# Full-Station Water Quality Database

This directory contains processed reference tables for the broader Shanghai water-quality station database. These tables support future multi-station extension and data inspection. The current enhanced model run in this repository is still centered on Wusongkou station 2586.

## Files

| File | Description |
| --- | --- |
| `station_catalog.csv` | Station metadata and availability summary for the processed station set. |
| `water_quality_daily_all_stations.csv` | Daily water-quality table for all included stations. |
| `water_quality_daily_all_stations_with_secchi.csv` | Daily water-quality table plus the turbidity-derived Secchi-depth proxy. |
| `multimodal_daily_all_stations_with_weather.csv` | Daily water-quality and matched weather table for all included stations. |
| `multimodal_daily_all_stations_modality_summary.csv` | Per-station modality coverage summary. |
| `station_weather_match_summary.csv` | Weather-station matching summary for each water-quality station. |
| `excluded_station_files.csv` | Stations excluded from the processed main table and the reason for exclusion. |
| `delivery_summary.json` | Structured summary for the processed database. |
| `file_inventory.csv` | Current file inventory for this directory. |

## Processing Scope

- Raw station files considered: 23.
- Stations included in the processed main database: 20.
- Stations excluded: 3.
- Total main daily rows: 31,099.
- Daily record span: 2014-04-03 to 2025-10-31.

The exact station-level row counts and modality coverage should be read from `station_catalog.csv` and `multimodal_daily_all_stations_modality_summary.csv`, because those files are the authoritative processed outputs.

## Main Fields

Common station fields:

- `station_code`
- `station_name`
- `province`
- `city`
- `basin`
- `river`
- `longitude`
- `latitude`
- `date`

Core water-quality fields:

- `water_temp`
- `ph`
- `dissolved_oxygen`
- `conductivity`
- `turbidity`
- `codmn`
- `nh3_n`
- `toc`
- `tp`
- `tn`
- `chlorophyll_a`
- `algae_density`
- `water_quality_class`
- `station_status`

Weather match fields:

- `weather_station_id`
- `weather_station_name`
- `weather_district`
- `weather_city`
- `weather_distance_km`
- `pressure`
- `air_temp`
- `humidity`
- `precipitation`
- `wind_speed`
- `wind_dir`

## Secchi Proxy

`secchi_depth_sd_m` is a turbidity-derived clearness proxy:

`SD = 1.5 / NTU^0.7`

This is a proxy feature for modeling and screening. It should not be presented as a direct field-measured Secchi depth unless field validation is added.

## Usage Notes

- Treat this directory as a processed reference database.
- Use `data/raw/` and `configs/default.yaml` to reproduce the current Wusongkou enhanced model run.
- Future multi-station modeling should first define station-level train/validation/test splits and hydrodynamic matching rules before training a joint model.

## Zhangjiabang Proxy Dataset

The repository now includes a Zhangjiabang East Gate proxy data build based on the existing full-station database:

- Water-quality proxy: station `2198` Sanjiagang.
- Weather proxy: station `58370` Pudong.
- Outputs: `data/proxy/zhangjiabang_proxy/zhangjiabang_proxy_daily.csv` and `data/proxy/zhangjiabang_proxy/zhangjiabang_proxy_summary.json`.
- Build script: `scripts/preprocess/build_zhangjiabang_proxy_dataset.py`.

This is a substitute dataset for access validation and future transfer/retraining work. It is not direct Zhangjiabang East Gate measurement data.
