from pyresample import load_area
from pyresample.bucket import BucketResampler
import h5py
import os
import dask.array as da
import xarray as xr
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from atrain_match.utils import validate_cph_util as vcu
from atrain_match.utils.get_flag_info import get_calipso_clouds_of_type_i_feature_classification_flags_one_layer as get_cal_flag
from scores import (hitrate, pod_clr, pod_cld, far_clr, far_cld, pofd_clr,
                    pofd_cld, heidke, kuiper, bias, mean)


matplotlib.use('Agg')

# --------------------------- CTTH ------------------------------------------
def get_caliop_cth(ds):
    cth = np.array(ds['layer_top_altitude'])[:, 0]
    elev = np.array(ds['elevation'])
    # set FillValue to NaN, convert to m
    cth = np.where(cth == -9999, np.nan, cth * 1000.)
    # compute height above surface
    cth_surf = cth - elev
    return cth_surf


def get_caliop_ctt(ds):
    ctt = np.array(ds['midlayer_temperature'])[:, 0]
    ctt = np.where(ctt == -9999, np.nan, ctt + 273.15)
    ctt = np.where(ctt < 0, np.nan, ctt)
    return ctt


def get_imager_cth(ds):
    alti = np.array(ds['ctth_height'])
    # set FillValue to NaN
    alti = np.where(alti < 0, np.nan, alti)
    # alti = np.where(alti>45000, np.nan, alti)
    return alti


def get_imager_ctt(ds):
    tempe = np.array(ds['ctth_temperature'])
    tempe = np.where(tempe < 0, np.nan, tempe)
    return tempe


def get_calipso_clouds_of_type_i(cflag, calipso_cloudtype=0):
    """Get CALIPSO clouds of type i from top layer."""
    # bits 10-12, start at 1 counting
    return get_cal_flag(cflag, calipso_cloudtype=calipso_cloudtype)


def get_calipso_low_clouds(cfalg):
    """Get CALIPSO low clouds."""
    # type 0, 1, 2, 3 are low cloudtypes
    calipso_low = np.logical_or(
        np.logical_or(
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=0),
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=1)),
        np.logical_or(
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=2),
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=3)))
    return calipso_low


def get_calipso_medium_clouds(cfalg):
    """Get CALIPSO medium clouds."""
    # type 4,5 are mid-level cloudtypes (Ac, As)
    calipso_high = np.logical_or(
        get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=4),
        get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=5))
    return calipso_high


def get_calipso_high_clouds(cfalg):
    """Get CALIPSO high clouds."""
    # type 6, 7 are high cloudtypes
    calipso_high = np.logical_or(
        get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=6),
        get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=7))
    return calipso_high


def get_calipso_op(cfalg):
    """Get CALIPSO opaque clouds."""
    # type 1, 2, 5, 7 are opaque cloudtypes
    calipso_low = np.logical_or(
        np.logical_or(
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=1),
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=2)),
        np.logical_or(
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=5),
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=7)))
    return calipso_low


def get_calipso_tp(cfalg):
    """Get CALIPSO semi-transparent clouds."""
    # type 0,3,4,6 transparent/broken
    calipso_low = np.logical_or(
        np.logical_or(
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=0),
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=3)),
        np.logical_or(
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=4),
            get_calipso_clouds_of_type_i(cfalg, calipso_cloudtype=6)))
    return calipso_low


def get_calipso_low_clouds_op(match_calipso):
    """Get CALIPSO low and opaque clouds."""
    # type 0, 1, 2, 3 are low cloudtypes
    calipso_low = np.logical_or(
        get_calipso_clouds_of_type_i(match_calipso, calipso_cloudtype=1),
        get_calipso_clouds_of_type_i(match_calipso, calipso_cloudtype=2))
    return calipso_low


def get_calipso_medium_and_high_clouds_tp(match_calipso):
    """Get CALIPSO medium transparent and high transparent clouds."""
    # type 0, 1, 2, 3 are low cloudtypes
    calipso_transp = np.logical_or(
        get_calipso_clouds_of_type_i(match_calipso, calipso_cloudtype=4),
        get_calipso_clouds_of_type_i(match_calipso, calipso_cloudtype=6))
    return calipso_transp


def get_caliop_cph(ds):
    """
    CALIPSO_PHASE_VALUES:   unknown=0,
                            ice=1,
                            water=2,
    """
    phase = vcu.get_calipso_phase_inner(ds['feature_classification_flags'],
                                        max_layers=10,
                                        same_phase_in_top_three_lay=True)
    mask = phase.mask
    phase = np.array(phase)
    phase = np.where(phase == 0, np.nan, phase)
    phase = np.where(phase == 2, 0, phase)
    phase = np.where(np.logical_or(phase == 1, phase == 3), 1, phase)

    phase = np.where(mask, np.nan, phase)
    return phase


def get_imager_cph(ds):
    phase = np.array(ds['cpp_phase'])
    phase = np.where(phase < 0, np.nan, phase)
    phase = np.where(phase > 10, np.nan, phase)
    phase = np.where(phase == 0, np.nan, phase)
    phase = np.where(phase == 1, 0, phase)
    phase = np.where(phase == 2, 1, phase)

    return phase


def get_caliop_cma(ds):
    cfrac_limit = 0.5
    caliop_cma = np.array(ds['cloud_fraction']) > cfrac_limit
    return caliop_cma.astype(bool)


def get_imager_cma(ds):
    data = np.array(ds['cloudmask'])
    binary = np.where(data == 0, 0, 1)
    binary = np.where(data < 0, np.nan, binary)

    return binary.astype(bool)


def get_collocated_file_info(ipath, chunksize, dnt='ALL',
                             satz_lim=None, dataset='CCI'):
    file = h5py.File(ipath, 'r')
    caliop = file['calipso']

    if dataset == 'CCI':
        imager = file['cci']
    elif dataset == 'CLAAS':
        imager = file['pps']
    else:
        raise Exception('Dataset {} not known!'.format(dataset))

    # get CTH and CTT
    sev_cth = da.from_array(get_imager_cth(imager), chunks=chunksize)
    cal_cth = da.from_array(get_caliop_cth(caliop), chunks=chunksize)
    sev_ctt = da.from_array(get_imager_ctt(imager), chunks=chunksize)
    cal_ctt = da.from_array(get_caliop_ctt(caliop), chunks=chunksize)
    cal_cflag = np.array(caliop['feature_classification_flags'][::, 0])

    # ctp_c = np.array(caliop['layer_top_pressure'])[:,0]
    # ctp_c = np.where(ctp_c == -9999, np.nan,ctp_c)
    # ctp_pps = np.array(imager['ctth_pressure'])
    # ctp_pps = np.where(ctp_pps==-9, np.nan, ctp_pps)
    # sev_ctp = da.from_array(ctp_pps, chunks=(chunksize))
    # cal_ctp = da.from_array(ctp_c, chunks=(chunksize))

    # get CMA, CPH, VZA, SZA, LAT and LON
    sev_cph = da.from_array(get_imager_cph(imager), chunks=chunksize)
    cal_cph = da.from_array(get_caliop_cph(caliop), chunks=chunksize)
    cal_cma = da.from_array(get_caliop_cma(caliop), chunks=chunksize)
    sev_cma = da.from_array(get_imager_cma(imager), chunks=chunksize)
    satz = da.from_array(imager['satz'], chunks=chunksize)
    sunz = da.from_array(imager['sunz'], chunks=chunksize)
    lat = da.from_array(imager['latitude'], chunks=chunksize)
    lon = da.from_array(imager['longitude'], chunks=chunksize)

    # mask satellize zenith angle
    if satz_lim is not None:
        mask = satz > satz_lim
        cal_cma = da.where(mask, np.nan, cal_cma)
        sev_cma = da.where(mask, np.nan, sev_cma)
        cal_cph = da.where(mask, np.nan, cal_cph)
        sev_cph = da.where(mask, np.nan, sev_cph)
        cal_cth = da.where(mask, np.nan, cal_cth)
        sev_cth = da.where(mask, np.nan, sev_cth)
        # cal_ctp = da.where(mask, np.nan, cal_ctt)
        # sev_ctp = da.where(mask, np.nan, sev_ctt)
    # mask all pixels except daytime
    if dnt == 'DAY':
        mask = sunz >= 80
        cal_cma = da.where(mask, np.nan, cal_cma)
        sev_cma = da.where(mask, np.nan, sev_cma)
        cal_cph = da.where(mask, np.nan, cal_cph)
        sev_cph = da.where(mask, np.nan, sev_cph)
        cal_cth = da.where(mask, np.nan, cal_cth)
        sev_cth = da.where(mask, np.nan, sev_cth)
        # cal_ctp = da.where(mask, np.nan, cal_ctt)
        # sev_ctp = da.where(mask, np.nan, sev_ctt)
    # mask all pixels except nighttime
    elif dnt == 'NIGHT':
        mask = sunz <= 95
        cal_cma = da.where(mask, np.nan, cal_cma)
        sev_cma = da.where(mask, np.nan, sev_cma)
        cal_cph = da.where(mask, np.nan, cal_cph)
        sev_cph = da.where(mask, np.nan, sev_cph)
        cal_cth = da.where(mask, np.nan, cal_cth)
        sev_cth = da.where(mask, np.nan, sev_cth)
        # cal_ctp = da.where(mask, np.nan, cal_ctt)
        # sev_ctp = da.where(mask, np.nan, sev_ctt)
    # mask all pixels except twilight
    elif dnt == 'TWILIGHT':
        mask = ~da.logical_and(sunz > 80, sunz < 95)
        cal_cma = da.where(mask, np.nan, cal_cma)
        sev_cma = da.where(mask, np.nan, sev_cma)
        cal_cph = da.where(mask, np.nan, cal_cph)
        sev_cph = da.where(mask, np.nan, sev_cph)
        cal_cth = da.where(mask, np.nan, cal_cth)
        sev_cth = da.where(mask, np.nan, sev_cth)
        # cal_ctp = da.where(mask, np.nan, cal_ctt)
        # sev_ctp = da.where(mask, np.nan, sev_ctt)
    elif dnt == 'ALL':
        pass
    else:
        raise Exception('DNT option ', dnt, ' is invalid.')

    data = {'caliop_cma': cal_cma,
            'imager_cma': sev_cma,
            'caliop_cph': cal_cph,
            'imager_cph': sev_cph,
            'satz': satz,
            'sunz': sunz,
            'caliop_cth': cal_cth,
            'imager_cth': sev_cth,
            'caliop_ctt': cal_ctt,
            'imager_ctt': sev_ctt,
            'caliop_cflag': cal_cflag}

    latlon = {'lat': lat,
              'lon': lon}

    return data, latlon


def do_cma_validation(data, adef, out_size, idxs):
    cal_cma = data['caliop_cma']
    img_cma = data['imager_cma']

    # pattern: CALIOP_SEVIRI
    cld_cld_a = da.logical_and(cal_cma == 1, img_cma == 1)
    clr_cld_b = da.logical_and(cal_cma == 0, img_cma == 1)
    cld_clr_c = da.logical_and(cal_cma == 1, img_cma == 0)
    clr_clr_d = da.logical_and(cal_cma == 0, img_cma == 0)

    cld_cld_a = cld_cld_a.astype(np.int64)
    clr_cld_b = clr_cld_b.astype(np.int64)
    cld_clr_c = cld_clr_c.astype(np.int64)
    clr_clr_d = clr_clr_d.astype(np.int64)

    a, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=cld_cld_a, density=False)
    b, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=clr_cld_b, density=False)
    c, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=cld_clr_c, density=False)
    d, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=clr_clr_d, density=False)

    n = a + b + c + d
    n2d = n.reshape(adef.shape)

    scores = dict()
    scores['Hitrate'] = [hitrate(a, d, n).reshape(adef.shape),
                         0.5, 1, 'rainbow']
    scores['PODclr'] = [pod_clr(b, d).reshape(adef.shape),
                        0.5, 1, 'rainbow']
    scores['PODcld'] = [pod_cld(a, c).reshape(adef.shape),
                        0.5, 1, 'rainbow']
    scores['FARclr'] = [far_clr(c, d).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['FARcld'] = [far_cld(a, b).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['POFDclr'] = [pofd_clr(a, c).reshape(adef.shape),
                         0, 1, 'rainbow']
    scores['POFDcld'] = [pofd_cld(b, d).reshape(adef.shape),
                         0, 1, 'rainbow']
    scores['Heidke'] = [heidke(a, b, c, d).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['Kuiper'] = [kuiper(a, b, c, d).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['Bias'] = [bias(b, c, n).reshape(adef.shape),
                      0, 1, 'bwr']
    scores['CALIOP mean'] = [mean(a, c, n).reshape(adef.shape),
                             None, None, 'rainbow']
    scores['SEVIRI mean'] = [mean(a, b, n).reshape(adef.shape),
                             None, None, 'rainbow']
    scores['Nobs'] = [n2d, None, None, 'rainbow']

    scores['Bias'][2] = np.nanmax(np.abs(scores['Bias'][0])) / 2
    scores['Bias'][1] = scores['Bias'][2] * (-1)
    return scores


def do_cph_validation(data, adef, out_size, idxs):
    cal_cph = data['caliop_cph']
    img_cph = data['imager_cph']

    # pattern: CALIOP_SEVIRI
    # get counts for contigency table
    ice_ice_a = da.logical_and(cal_cph == 1, img_cph == 1)
    liq_ice_b = da.logical_and(cal_cph == 0, img_cph == 1)
    ice_liq_c = da.logical_and(cal_cph == 1, img_cph == 0)
    liq_liq_d = da.logical_and(cal_cph == 0, img_cph == 0)
    ice_ice_a = ice_ice_a.astype(np.int64)
    liq_ice_b = liq_ice_b.astype(np.int64)
    ice_liq_c = ice_liq_c.astype(np.int64)
    liq_liq_d = liq_liq_d.astype(np.int64)

    # use histogram functionality to get contigency table summed up for every
    # grid box in target grid
    a, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=ice_ice_a, density=False)
    b, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=liq_ice_b, density=False)
    c, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=ice_liq_c, density=False)
    d, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=liq_liq_d, density=False)

    n = a + b + c + d
    n2d = n.reshape(adef.shape)

    # calculate scores
    scores = dict()
    scores['Hitrate'] = [hitrate(a, d, n).reshape(adef.shape),
                         0.5, 1, 'rainbow']
    scores['PODliq'] = [pod_clr(b, d).reshape(adef.shape),
                        0.5, 1, 'rainbow']
    scores['PODice'] = [pod_cld(a, c).reshape(adef.shape),
                        0.5, 1, 'rainbow']
    scores['FARliq'] = [far_clr(c, d).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['FARice'] = [far_cld(a, b).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['POFDliq'] = [pofd_clr(a, c).reshape(adef.shape),
                         0, 1, 'rainbow']
    scores['POFDice'] = [pofd_cld(b, d).reshape(adef.shape),
                         0, 1, 'rainbow']
    scores['Heidke'] = [heidke(a, b, c, d).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['Kuiper'] = [kuiper(a, b, c, d).reshape(adef.shape),
                        0, 1, 'rainbow']
    scores['Bias'] = [bias(b, c, n).reshape(adef.shape),
                      0, 1, 'bwr']
    scores['CALIOP mean'] = [mean(a, c, n).reshape(adef.shape),
                             None, None, 'rainbow']
    scores['SEVIRI mean'] = [mean(a, b, n).reshape(adef.shape),
                             None, None, 'rainbow']
    scores['Nobs'] = [n2d, None, None, 'rainbow']

    scores['Bias'][2] = np.nanmax(np.abs(scores['Bias'][0])) / 2
    scores['Bias'][1] = scores['Bias'][2] * (-1)

    return scores


def do_ctth_validation(data, resampler, thrs=10):
    """ thrs: threshold value for filtering boxes with small number of obs """
    # mask of detected ctth
    detected_clouds = da.logical_and(data['caliop_cma'] == 1,
                                     data['imager_cma'] == 1)
    detected_height = da.logical_and(detected_clouds,
                                     np.isfinite(data['imager_cth']))
    detected_temperature = np.logical_and(detected_clouds,
                                          np.isfinite(data['imager_ctt']))
    detected_height_mask = detected_height.astype(int)

    # calculate bias and mea for all ctth cases
    delta_h = data['imager_cth'] - data['caliop_cth']  # HEIGHT
    height_bias = np.where(detected_height, delta_h, np.nan)
    mae = np.abs(height_bias)
    delta_t = data['imager_ctt'] - data['caliop_ctt']  # TEMPERATURE
    temperature_bias = np.where(detected_temperature, delta_t, np.nan)

    # clouds levels (from calipso 'cloud type')
    low_clouds = get_calipso_low_clouds(data['caliop_cflag'])
    detected_low = np.logical_and(detected_height, low_clouds)
    bias_low = np.where(detected_low, height_bias, np.nan)
    bias_temperature_low = np.where(detected_low, temperature_bias, np.nan)
    mid_clouds = get_calipso_medium_clouds(data['caliop_cflag'])
    detected_mid = np.logical_and(detected_height, mid_clouds)
    bias_mid = np.where(detected_mid, height_bias, np.nan)
    high_clouds = get_calipso_high_clouds(data['caliop_cflag'])
    detected_high = np.logical_and(detected_height, high_clouds)
    bias_high = np.where(detected_high, height_bias, np.nan)
    # opaque/transparent clouds (from calipso 'cloud type')
    # tp_clouds = get_calipso_tp(data['caliop_cflag'])
    # detected_tp = np.logical_and(detected_height,tp_clouds)
    # bias_tp = np.where(detected_tp, height_bias, np.nan)
    # op_clouds = get_calipso_op(data['caliop_cflag'])
    # detected_op = np.logical_and(detected_height,op_clouds)
    # bias_op = np.where(detected_op, height_bias, np.nan)
    # low+opaque, mid/high+transparent
    mid_high_tp_clouds = get_calipso_medium_and_high_clouds_tp(
                                                data['caliop_cflag']
                                                )
    detected_mid_high_tp = np.logical_and(detected_height, mid_high_tp_clouds)
    bias_mid_high_tp = np.where(detected_mid_high_tp, height_bias, np.nan)
    low_op_clouds = get_calipso_low_clouds_op(data['caliop_cflag'])
    detected_low_op = np.logical_and(detected_height, low_op_clouds)
    bias_low_op = np.where(detected_low_op, height_bias, np.nan)

    # resample and filter some data out
    # N = resampler.get_count()
    n_matched_cases = resampler.get_sum(detected_height_mask)
    sev_cth_average = resampler.get_average(data['imager_cth'])
    cal_cth_average = resampler.get_average(data['caliop_cth'])
    bias_average = resampler.get_average(height_bias)
    bias_average = np.where(n_matched_cases < thrs, np.nan, bias_average)
    mae_average = resampler.get_average(mae)
    mae_average = np.where(n_matched_cases < thrs, np.nan, mae_average)
    bias_temperature_average = resampler.get_average(temperature_bias)
    bias_temperature_average = np.where(n_matched_cases < thrs, np.nan,
                                        bias_temperature_average)

    n_matched_cases_low = resampler.get_sum(detected_low.astype(int))
    bias_low_average = resampler.get_average(bias_low)
    bias_low_average = np.where(n_matched_cases_low < thrs,
                                np.nan, bias_low_average)
    bias_temperature_low_average = resampler.get_average(bias_temperature_low)
    bias_temperature_low_average = np.where(n_matched_cases_low < thrs, np.nan,
                                            bias_temperature_low_average)
    n_matched_cases_mid = resampler.get_sum(detected_mid.astype(int))
    bias_mid_average = resampler.get_average(bias_mid)
    bias_mid_average = np.where(n_matched_cases_mid < thrs, np.nan,
                                bias_mid_average)
    n_matched_cases_high = resampler.get_sum(detected_high.astype(int))
    bias_high_average = resampler.get_average(bias_high)
    bias_high_average = np.where(n_matched_cases_high < thrs, np.nan,
                                 bias_high_average)

    # n_matched_cases_tp = resampler.get_sum(detected_tp.astype(int))
    # bias_tp_average = resampler.get_average(bias_tp)
    # bias_tp_average = np.where(n_matched_cases_tp<thrs,
    # np.nan, bias_tp_average)
    # n_matched_cases_op = resampler.get_sum(detected_op.astype(int))
    # bias_op_average = resampler.get_average(bias_op)
    # bias_op_average = np.where(n_matched_cases_op<thrs,
    # np.nan, bias_op_average)

    n_matched_cases_mid_high_tp = resampler.get_sum(
                                        detected_mid_high_tp.astype(int)
                                        )
    bias_mid_high_tp_average = resampler.get_average(bias_mid_high_tp)
    bias_mid_high_tp_average = np.where(n_matched_cases_mid_high_tp < thrs,
                                        np.nan, bias_mid_high_tp_average)
    n_matched_cases_low_op = resampler.get_sum(detected_low_op.astype(int))
    bias_low_op_average = resampler.get_average(bias_low_op)
    bias_low_op_average = np.where(n_matched_cases_low_op < thrs,
                                   np.nan, bias_low_op_average)

    # calculate scores
    scores = dict()
    scores['Bias CTH'] = [bias_average, -4000, 4000, 'bwr']
    scores['MAE CTH'] = [mae_average, 0, 2500, 'Reds']

    scores['Bias low'] = [bias_low_average, -2000, 2000, 'bwr']
    scores['Bias middle'] = [bias_mid_average, -2000, 2000, 'bwr']
    scores['Bias high'] = [bias_high_average, -6000, 6000, 'bwr']

    # scores['Bias opaque'] = [bias_op_average, -4000, 4000, 'bwr']
    # scores['Bias transparent'] = [bias_tp_average, -4000, 4000, 'bwr']
    scores['Bias low opaque'] = [bias_low_op_average, -2000, 2000, 'bwr']
    scores['Bias mid+high transparent'] = [bias_mid_high_tp_average,
                                           -6000, 6000, 'bwr']

    scores['Bias temperature'] = [bias_temperature_average, -30, 30, 'bwr']
    scores['Bias temperature low'] = [bias_temperature_low_average,
                                      -10, 10, 'bwr']

    scores['CALIOP CTH mean'] = [cal_cth_average, 1000, 14000, 'rainbow']
    scores['SEVIRI CTH mean'] = [sev_cth_average, 1000, 14000, 'rainbow']
    scores['Num_detected_height'] = [n_matched_cases, None, None, 'rainbow']

    # addit_scores = do_ctp_validation(data, adef, out_size, idxs)
    # scores.update(addit_scores)

    # scores['N_matched_cases_low'] = [N_matched_cases_low,
    # None, None, 'rainbow']
    # scores['N_matched_cases_middle'] = [N_matched_cases_mid,
    # None, None, 'rainbow']
    # scores['N_matched_cases_high'] = [N_matched_cases_high,
    # None, None, 'rainbow']
    return scores


def do_ctp_validation(data, adef, out_size, idxs):
    """ Scores: low clouds detection """
    # detected ctth mask
    detected_clouds = da.logical_and(data['caliop_cma'] == 1,
                                     data['imager_cma'] == 1)
    detected_height = da.logical_and(detected_clouds,
                                     np.isfinite(data['imager_cth']))
    # find pps low and caliop low
    low_clouds_c = get_calipso_low_clouds(data['caliop_cflag'])
    detected_low_c = np.logical_and(detected_height, low_clouds_c)
    low_clouds_pps = da.where(data['imager_ctp'] > 680., 1, 0)
    detected_low_pps = da.logical_and(detected_height, low_clouds_pps)

    # pattern: CALIOP_SEVIRI
    cld_cld_a = da.logical_and(detected_low_c == 1, detected_low_pps == 1)
    clr_cld_b = da.logical_and(detected_low_c == 0, detected_low_pps == 1)
    cld_clr_c = da.logical_and(detected_low_c == 1, detected_low_pps == 0)
    clr_clr_d = da.logical_and(detected_low_c == 0, detected_low_pps == 0)

    cld_cld_a = cld_cld_a.astype(np.int64)
    clr_cld_b = clr_cld_b.astype(np.int64)
    cld_clr_c = cld_clr_c.astype(np.int64)
    clr_clr_d = clr_clr_d.astype(np.int64)

    a, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=cld_cld_a, density=False)
    b, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=clr_cld_b, density=False)
    c, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=cld_clr_c, density=False)
    d, _ = da.histogram(idxs, bins=out_size, range=(0, out_size),
                        weights=clr_clr_d, density=False)

    # n = a + b + c + d
    # n2d = N.reshape(adef.shape)

    # scores = [hitrate(a, d, n).reshape(adef.shape),
    # 0.7, 1, 'rainbow'] # hitrate low PPS
    pod_low = a / (a + c)
    far_low = c / (a + c)
    scores = dict()
    scores['POD low clouds'] = [pod_low.reshape(adef.shape), 0.2, 1, 'rainbow']
    scores['FAR low clouds'] = [far_low.reshape(adef.shape), 0.2, 1, 'rainbow']

    return scores


def get_cosfield(lat):
    latcos = np.abs(np.cos(lat * np.pi / 180))
    cosfield = da.from_array(latcos, chunks=(1000, 1000))  # [mask]
    return cosfield


def weighted_spatial_average(data, cosfield):
    if isinstance(data, xr.DataArray):
        data = data.data
    if isinstance(data, np.ndarray):
        data = da.from_array(data, chunks=(1000, 1000))
    return da.nansum(data * cosfield) / da.nansum(cosfield)


def make_plot(scores, optf, crs, dnt, var, cosfield):
    fig = plt.figure(figsize=(16, 7))
    for cnt, s in enumerate(scores.keys()):
        values = scores[s]
        values[0] = da.where(scores['Nobs'][0] < 50, np.nan, values[0])
        ax = fig.add_subplot(4, 4, cnt + 1, projection=crs)
        ims = ax.imshow(values[0],
                        transform=crs,
                        extent=crs.bounds,
                        vmin=values[1],
                        vmax=values[2],
                        cmap=plt.get_cmap(values[3]),
                        origin='upper',
                        interpolation='none'
                        )
        ax.coastlines(color='black')
        # mean = weighted_spatial_average(values[0], cosfield).compute()
        # mean = '{:.2f}'.format(da.nanmean(values[0]).compute())
        mean = ''
        ax.set_title(var + ' ' + s + ' ' + dnt + ' {}'.format(mean))
        plt.colorbar(ims)
    plt.tight_layout()
    plt.savefig(optf)
    print('SAVED ', os.path.basename(optf))


def make_plot_CTTH(scores, optf, crs, dnt, var, cosfield):
    fig = plt.figure(figsize=(16, 12))
    for cnt, s in enumerate(scores.keys()):
        values = scores[s]
        masked_values = np.ma.array(values[0], mask=np.isnan(values[0]))
        cmap = plt.get_cmap(values[3])
        cmap.set_bad('grey', 1.)
        ax = fig.add_subplot(4, 3, cnt + 1, projection=crs)  # ccrs.Robinson()
        ims = ax.imshow(masked_values,
                        transform=crs,
                        extent=crs.bounds,
                        vmin=values[1],
                        vmax=values[2],
                        cmap=cmap,
                        origin='upper',
                        interpolation='none'
                        )
        ax.coastlines(color='black')
        # mean = ''
        mean = weighted_spatial_average(values[0], cosfield).compute()
        mean = '{:.2f}'.format(da.nanmean(values[0]).compute())
        ax.set_title(var + ' ' + s + ' ' + dnt + ' {}'.format(mean))
        plt.colorbar(ims)
    plt.tight_layout()
    plt.savefig(optf)
    plt.close()
    print('SAVED ', os.path.basename(optf))


def make_scatter(data, optf, dnt, dataset):
    from scipy.stats import linregress
    from matplotlib.colors import LogNorm

    fig = plt.figure(figsize=(12, 4))
    # variable to be plotted
    vars = ['cth', 'ctt']
    # limits for plotting
    lims = {'cth': (0, 25), 'ctt': (150, 325)}
    # units for plotting
    units = {'cth': 'km', 'ctt': 'm'}

    for cnt, variable in enumerate(vars):
        x = data['imager_' + variable].compute()
        y = data['caliop_' + variable].compute()

        # divide CCI CTH by 1000 to convert from m to km
        if variable == 'cth' and dataset == 'CCI':
            x /= 1000
            y /= 1000

        # dummy data for 1:1 line
        dummy = np.arange(0, lims[variable][1])

        # remove nans in both arrays
        mask = np.logical_or(np.isnan(x), np.isnan(y))
        x = x[~mask]
        y = y[~mask]

        ax = fig.add_subplot(1, 2, cnt + 1)
        h = ax.hist2d(x, y,
                      bins=(100, 100),
                      cmap=plt.get_cmap('YlOrRd'),
                      norm=LogNorm())

        # make linear regression
        reg = linregress(x, y)
        # plot linear regression
        ax.plot(reg[0] * dummy + reg[1], color='blue')
        # plot 1:1 line
        ax.plot(dummy, dummy, color='black')

        ax.set_xlabel('imager_{} [{}]'.format(variable, units[variable]))
        ax.set_ylabel('caliop_{} [{}]'.format(variable, units[variable]))
        ax.set_xlim(lims[variable])
        ax.set_ylim(lims[variable])
        ax.set_title(variable.upper() + ' ' + dnt, fontweight='bold')
        # write regression parameters to plot
        ax.annotate(xy=(0.05, 0.9),
                    s='r={:.2f}\nr**2={:.2f}'.format(reg[2], reg[2] * reg[2]),
                    xycoords='axes fraction', color='blue', fontweight='bold',
                    backgroundcolor='lightgrey')

        plt.colorbar(h[3], ax=ax)

    plt.tight_layout()
    plt.savefig(optf)
    plt.close()
    print('SAVED ', os.path.basename(optf))


def run(ipath, ifile, opath, dnts, satzs,
        year, month, dataset, chunksize=100000):
    # if dnts is single string convert to list
    if isinstance(dnts, str):
        dnts = [dnts]

    # if satzs is single string/int/float convert to list
    if isinstance(satzs, str) or isinstance(satzs, int) or isinstance(satzs, float):
        satzs = [satzs]

    if dataset not in ['CCI', 'CLAAS3']:
        raise Exception('Dataset {} not available!'.format(dataset))

    ofile_cma = 'CMA_SEVIRI_CALIOP_{}{}_DNT-{}_SATZ-{}.png'
    ofile_cph = 'CPH_SEVIRI_CALIOP_{}{}_DNT-{}_SATZ-{}.png'
    ofile_ctth = 'CTTH_SEVIRI_CALIOP_{}{}_DNT-{}_SATZ-{}.png'
    ofile_scat = 'SCATTER_SEVIRI_CALIOP_{}{}_DNT-{}_SATZ-{}.png'

    # iterate over satzen limitations
    for satz_lim in satzs:

        # if satz_lim list item is string convert it to float
        if satz_lim is not None:
            if isinstance(satz_lim, str):
                try:
                    satz_lim = float(satz_lim)
                except ValueError:
                    msg = 'Cannot convert {} to float'
                    raise Exception(msg.format(satz_lim))

        for dnt in dnts:

            dnt = dnt.upper()
            if dnt not in ['ALL', 'DAY', 'NIGHT', 'TWILIGHT']:
                raise Exception('DNT {} not recognized'.format(dnt))

            # set output filenames for CPH and CMA plot
            ofile_cma = ofile_cma.format(year, month, dnt, satz_lim)
            ofile_cph = ofile_cph.format(year, month, dnt, satz_lim)
            ofile_ctth = ofile_ctth.format(year, month, dnt, satz_lim)
            ofile_scat = ofile_scat.format(year, month, dnt, satz_lim)

            # get matchup data
            data, latlon = get_collocated_file_info(os.path.join(ipath, ifile),
                                                    chunksize, dnt, satz_lim,
                                                    dataset)

            adef = load_area('areas.yaml', 'pc_world')

            # for each input pixel get target pixel index
            resampler = BucketResampler(adef, latlon['lon'], latlon['lat'])
            idxs = resampler.idxs

            # get output grid size/lat/lon
            out_size = adef.size
            lon, lat = adef.get_lonlats()

            # do validation
            cma_scores = do_cma_validation(data, adef, out_size, idxs)
            cph_scores = do_cph_validation(data, adef, out_size, idxs)
            ctth_scores = do_ctth_validation(data, resampler, thrs=10)

            # get crs for plotting
            crs = adef.to_cartopy_crs()

            # get cos(lat) filed for weighted average on global regular grid
            cosfield = get_cosfield(lat)

            # do plotting
            make_plot(cma_scores, os.path.join(opath, ofile_cma), crs,
                      dnt, 'CMA', cosfield)
            make_plot(cph_scores, os.path.join(opath, ofile_cph), crs,
                      dnt, 'CPH', cosfield)
            make_plot_CTTH(ctth_scores, os.path.join(opath, ofile_ctth),
                           crs, dnt, 'CTTH', cosfield)
            make_scatter(data, os.path.join(opath, ofile_scat), dnt, dataset)
