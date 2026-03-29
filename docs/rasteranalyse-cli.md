# Rasteranalyse med CLI

Denne leveransen bruker DEM-filen som allerede ligger i repoet:

`Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem`

## Kjor analysen lokalt

```powershell
python scripts/raster_analysis.py `
  --dem Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem `
  --output-dir outputs/rasteranalyse `
  --slope-threshold 30
```

Dette lager:

- `outputs/rasteranalyse/slope_degrees.tif`
- `outputs/rasteranalyse/steep_gt_30deg.tif`
- `outputs/rasteranalyse/steep_gt_30deg.geojson`
- `outputs/rasteranalyse/hillshade_standard_az315_alt45_z1.0.tif`
- `outputs/rasteranalyse/hillshade_dramatic_az225_alt30_z1.6.tif`

## Ekvivalente GDAL-kommandoer

Miljoet i repoet har ikke `gdaldem` i PATH, sa den lokale kjoringen bruker Python-scriptet over. Hvis du har GDAL installert, er dette kommandoene som tilsvarer oppgaven:

```powershell
gdaldem slope Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem outputs/rasteranalyse/slope_degrees.tif -of GTiff -compute_edges
gdal_calc.py -A outputs/rasteranalyse/slope_degrees.tif --outfile=outputs/rasteranalyse/steep_gt_30deg.tif --calc=\"A>30\" --NoDataValue=255 --type=Byte
gdal_polygonize.py outputs/rasteranalyse/steep_gt_30deg.tif -f GeoJSON outputs/rasteranalyse/steep_gt_30deg.geojson steep steep
gdaldem hillshade Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem outputs/rasteranalyse/hillshade_standard_az315_alt45_z1.0.tif -of GTiff -az 315 -alt 45 -z 1.0 -compute_edges
gdaldem hillshade Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem outputs/rasteranalyse/hillshade_dramatic_az225_alt30_z1.6.tif -of GTiff -az 225 -alt 30 -z 1.6 -compute_edges
```

## Egne hillshade-parametere

Du kan lage andre hillshade-varianter ved a gjenta `--hillshade`:

```powershell
python scripts/raster_analysis.py `
  --dem Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem `
  --output-dir outputs/rasteranalyse `
  --slope-threshold 30 `
  --hillshade bright_terrain:315:55:1.0 `
  --hillshade low_sun:200:20:2.0
```
