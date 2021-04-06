from typing import List
import glob
import datetime
from flask import jsonify
from tensorflow import keras
#from osgeo import gdal_array
from skimage import io

import gdal
import os
import numpy as np

from ..utils import (
    get_raster_size,
    get_raster_resolution,
    get_raster_extent,
    get_raster_projection,
    get_bands,
    check_rasters_list,
    get_raster_path
)

TEMP_WARP_FLD = os.path.normpath("./processing/temp/warp")
TEMP_STACK_FLD = os.path.normpath("./processing/temp/stack")
TEMP_TILES_FLD = os.path.normpath("./processing/temp/tiles")
TEMP_PREDICT_FLD = os.path.normpath("./processing/temp/predicts")
STATIC_FLD = os.path.normpath("./static")
IMG_FLD = os.path.normpath('./data/aviable_images')  # relative from main.py


def stack_layers(sampleFld: str, oldList: List, newList: List, outFld: str, outName: str, features_count: int = 16):
    """
    Stack layers in one raster (now of the same resolution)
    and calculate difference

    :param sampleFld:str folder with original images (old or new) used for get information about raster
    :param oldList: band list from first image expected in order B04, B08, B11, B12
    :param newList: band list from first image expected in order B04, B08, B11, B12
    :param inputRasterPathsList: input init rasters for model
    :param outFld:
    :param outName:
    :param features_count: Number of input feature for model predict
    :return:
    """

    #sample_raster = oldList[0]
    # if resolution 60
    sample_raster = get_raster_path(sampleFld, "B01", IMG_FLD)
    # if resolution 20
    # sample_raster = get_raster_path(sampleFld, "B05", IMG_FLD)

    x_ncells, y_ncells = get_raster_size(sample_raster)
    cellsize = get_raster_resolution(sample_raster)

    x_min, x_max, y_min, y_max = get_raster_extent(sample_raster)
    output_tiff = os.path.join(outFld, outName)

    # create output (spatial ref from first raster)
    out_driver = gdal.GetDriverByName('GTiff')
    out_source = out_driver.Create(
        output_tiff,
        x_ncells,
        y_ncells,
        features_count,
        gdal.GDT_UInt16
    )
    out_source.SetGeoTransform((x_min, cellsize, 0, y_max, 0, -cellsize))
    out_source.SetProjection(get_raster_projection(newList[0]))

    idx_map = [
        [1, 3, 5, 6],  # B04
        # [new channel index, old channel index, new - old dif index, old - new dif index]
        [2, 4, 7, 8],  # B08
        [13, 14, 15, 16],  # B11
        [9, 10, 11, 12]  # B12
    ]

    # writing original data
    # indexes of new channel in out raster
    for oldRaster, newRaster, idxs in zip(oldList, newList, idx_map):
        old_idx, new_idx, dif1_idx, dif2_idx = idxs
        old = gdal.Open(oldRaster).ReadAsArray()
        new = gdal.Open(newRaster).ReadAsArray()
        dif1 = new - old
        dif2 = old - new

        out_source.GetRasterBand(old_idx).WriteArray(old)
        out_source.GetRasterBand(new_idx).WriteArray(new)
        out_source.GetRasterBand(dif1_idx).WriteArray(dif1)
        out_source.GetRasterBand(dif2_idx).WriteArray(dif2)

        old = None
        new = None

    out_source = None

    return output_tiff


def raster2tile(inRaster, outFolder, tileSize=512):
    """
    Split raster to chunks (512 to 512)
    """
    import subprocess

    print(" ".join([
        '"venv/Scripts/python"',
        '"venv/Scripts/gdal_retile.py"',
        f' -ps {tileSize} {tileSize}',
        f' -targetDir "{os.path.normpath(outFolder)}"',
        f' "{os.path.normpath(inRaster)}"'
    ]))

    width = 5490
    height = 5490
    tilesize = 256


    for i in range(0, width, tilesize):
        for j in range(0, height, tilesize):

            opts = gdal.TranslateOptions(
                format="GTiff",
                srcWin=[i, j, tilesize, tilesize],
            )

            gdal.Translate(os.path.join(outFolder, f"tile_{i}_{j}.tif"), inRaster, options=opts)


def merge_tiles(inFld, outFile):
    """
    Merge all predicted tiles to one file
    :param inFld: folder with predicted tiles
    :param outFile: merged geotiff file with extension
    :return:
    """
    lsTfs = glob.glob(f'{inFld}/*.tif')

    bltOpts = gdal.BuildVRTOptions()
    ds = gdal.BuildVRT('mosaic.vrt', lsTfs, options=bltOpts)

    outDs = gdal.GetDriverByName("GTiff").Create(
        outFile,
        ds.RasterXSize,
        ds.RasterYSize,
        1,
        gdal.GDT_Float32
    )

    outDs.GetRasterBand(1).WriteArray(ds.ReadAsArray().astype(np.float32))
    srsSpRef = ds.GetSpatialRef()

    outDs.SetProjection(srsSpRef.ExportToWkt())
    outDs.SetGeoTransform(ds.GetGeoTransform())

    ds = None
    outDs = None


def predict_folder(
        model_path='./files/winterBackboneFirstTest.h5',
        inFld='../../ds/ds_validation_256_256_26/L1C_T40VEM_A024828_20200324T073608_L1C_T40VEM_A014132_20191120T074121/',
        outFld='/home/andrew.tarasov1993.gmail.com/outs/geoRefPredict'
               '/L1C_T40VEM_A024828_20200324T073608_L1C_T40VEM_A014132_20191120T074121'
):
    model = keras.models.load_model(model_path, compile=False)

    print(datetime.datetime.now())
    for img in os.listdir(inFld):
        # print (img)

        if img.endswith('.tif'):
            inImg = os.path.join(inFld, img)
            outTile = os.path.join(outFld, img)
            tileSize = 256

            #rasterArray = gdal_array.LoadFile(np.array(inImg))
            rasterArray = np.array(io.imread(inImg)/65536)
            #print(rasterArray.shape)
            if rasterArray.shape[0] != 256 or rasterArray.shape[1] != 256:
                # print (f"{img} - incorrect shape")
                rasterArray = None
                continue

            # print(inImg)
            # srcDs = gdal.Open(inImg)

            testPrediction = model.predict(np.array([rasterArray]))

            srcDs = gdal.Open(inImg)
            driver = gdal.GetDriverByName("GTiff")
            srsSpRef = srcDs.GetSpatialRef()

            dstDs = driver.Create(outTile, tileSize, tileSize, 1, gdal.GDT_Float32)
            dstDs.SetProjection(srsSpRef.ExportToWkt())
            dstDs.SetGeoTransform(srcDs.GetGeoTransform())

            dstDs.GetRasterBand(1).WriteArray(testPrediction[0][:, :, 0].astype(np.float32))
            # dstDs.FlushCache()
            dstDs = None
            src = None
    print(datetime.datetime.now())


def predict_pipeline(oldImg, newImg, warpFolder=TEMP_WARP_FLD, stackFolder=TEMP_STACK_FLD, resolution=20):

        # s2 bands
        # ["B01","B02","B03","B04","B05","B06","B07","B08","B8A","B09","B10","B11","B12"]

        featuresOld = get_bands(oldImg, ["B04", "B08", "B11", "B12"],
                               imgFolder=IMG_FLD)

        featuresNew = get_bands(newImg, ["B04", "B08", "B11", "B12"],
                               imgFolder=IMG_FLD)
        # print (featuresOld,'\n',featuresNew)
        print("Resolution checking")
        checkedRastersOld = check_rasters_list(featuresOld, resolution, warpFolder)
        checkedRastersNew = check_rasters_list(featuresNew, resolution, warpFolder)

        print("Stacking")
        outStack = os.path.join(stackFolder, f'{oldImg}_{newImg}.tif')
        if not os.path.exists(outStack):
            #return jsonify({'status':"already created"})
            outStack = stack_layers(
                sampleFld=oldImg,
                oldList=checkedRastersOld,
                newList=checkedRastersNew,
                outFld=TEMP_STACK_FLD,
                outName=f'{oldImg}_{newImg}.tif'
            )

        #return jsonify({'status': "created"})

        rasterName = os.path.basename(outStack).split('.tif')[0]
        tilesFolderPath = os.path.join(TEMP_TILES_FLD, rasterName)

        print("Tiling")
        if not os.path.exists(tilesFolderPath):
            os.mkdir(tilesFolderPath)
            raster2tile(outStack, tilesFolderPath, 256)

        print("Predict")
        model = os.path.join(STATIC_FLD, "AllMyUnet_36.h5")
        outPredictPath = os.path.join(TEMP_PREDICT_FLD, rasterName)
        if not os.path.exists(outPredictPath):
            os.mkdir(outPredictPath)
            predict_folder(model, tilesFolderPath, outPredictPath)

        print("Merge predict")
        outRaster = os.path.join(TEMP_PREDICT_FLD, rasterName + '.tif')
        merge_tiles(outPredictPath, outRaster)