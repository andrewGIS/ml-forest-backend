import os
import gdal
import glob


def get_raster_size(rasterPath):
    """
    Get raster size in pixel
    """
    infoOptions = gdal.InfoOptions(format='json')
    return gdal.Info(rasterPath, options=infoOptions)['size']


def get_raster_resolution(rasterPath):
    """
    Get raster pixel size
    """
    infoOptions = gdal.InfoOptions(format='json')
    return gdal.Info(rasterPath, options=infoOptions)["geoTransform"][1]


def get_raster_extent(rasterPath):
    """
    Get raster extent
    """

    infoOptions = gdal.InfoOptions(format='json')
    infoResult = gdal.Info(rasterPath, options=infoOptions)
    # return as -te <xmin> <ymin> <xmax> <ymax>
    return ((infoResult["cornerCoordinates"]['lowerLeft'])
            + (infoResult["cornerCoordinates"]['upperRight']))


def get_raster_projection(rasterPath):
    """
    Get raster projection
    """

    infoOptions = gdal.InfoOptions(format='json')
    infoResult = gdal.Info(rasterPath, options=infoOptions)
    # return as -te <xmin> <ymin> <xmax> <ymax>
    return infoResult["coordinateSystem"]['wkt']


def get_raster_path(imgFld,
                  channelTemplate="B08",
                  allImgFld=r"../addDataUsedImgs/"):
    """
    Get raster path of template channel
    """

    findString = os.path.normpath(f'''{allImgFld}//{imgFld}//**//*{channelTemplate}.jp2''')
    print(findString)
    findResults = glob.glob(findString, recursive=True)

    if len(findResults) != 1:
        raise ValueError(f'Template raster shoud be uniq or exists!, not {len(findResults)}')

    return findResults[0]


def get_bands(inputFld, bandsList, imgFolder='./'):
    """
    Return list of raster path to neccesary bands
    """
    avialableBands = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12"]

    outPaths = []
    for channel in bandsList:
        if channel not in avialableBands:
            ValueError(f'Channel {channel} not exists !')
        outPaths.append(get_raster_path(inputFld, channelTemplate=channel, allImgFld=imgFolder))

    return outPaths



def raster2tile(inRaster, outFolder, tileSize=512):
    """
    Split raster to chunks (512 to 512)
    """
    import subprocess

    if not os.path.exists(outFolder):
        os.mkdir(outFolder)

    print(" ".join([
        '"/home/gis/anaconda3/envs/geoTools/bin/python"',
        '"/home/gis/anaconda3/envs/geoTools/bin/gdal_retile.py"',
        f' -ps {tileSize} {tileSize}',
        f' -targetDir "{os.path.normpath(outFolder)}"',
        f' "{os.path.normpath(inRaster)}"'
    ]))
    subprocess.call(
        " ".join([
            '"/home/gis/anaconda3/envs/geoTools/bin/python"',
            '"/home/gis/anaconda3/envs/geoTools/bin/gdal_retile.py"',
            f' -ps {tileSize} {tileSize}',
            f' -targetDir "{os.path.normpath(outFolder)}"',
            f' "{os.path.normpath(inRaster)}"'
        ]),
        shell=True
    )


def resample_raster(inRaster, outRaster, outResolution):
    """
    Resample raster to other spatial resolution
    """
    warpOptions = gdal.WarpOptions(xRes=outResolution, yRes=outResolution)
    if os.path.exists(outRaster):
        return outRaster
    gdal.Warp(outRaster, inRaster, options=warpOptions)

    return outRaster


def check_rasters_list(inputList, targetResolution, wrapFld):
    """
    Check resolution for all rasters in list
    If resolution are other wrap it
    and replace data in list
    """
    for index, raster in enumerate(inputList):
        if not get_raster_resolution(raster) == targetResolution:
            print("Find raster with other resolution, warp")
            rasterName = os.path.basename(raster).replace('.jp2', '.tif')
            outRaster = os.path.join(wrapFld, rasterName)
            if os.path.exists(outRaster):
                inputList[index] = outRaster
                continue
            resampledRaster = resample_raster(raster, outRaster, targetResolution)
            inputList[index] = outRaster
    return inputList