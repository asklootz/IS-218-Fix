# Rasteranalyse

## 1. Kode- og repooversikt

Jeg gikk gjennom repoet for rasteroppgaven ble lost.

- `IS-218-Oppg2.ipynb` er hovedfilen i prosjektet og handler om befolkning vs. tilfluktsrom.
- Notebooken er delt i fire hoveddeler: pakkeimport, nedlasting/klargjoring av geodata, radiusanalyse og interaktiv kartvisning/eksport.
- Lokal befolkningsdata finnes i `data/GPKG_befolkning_250m_2025.gpkg`.
- Lokal befolkningsdata finnes ogsa i `data/geoJSON_befolkning_250m_2025.geojson`.
- Lokal hoydedata finnes i `Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem`.
- Notebooken ble ikke endret. Rasterleveransen ligger separat i `raster-output/`.

## 2. DEM brukt i analysen

Repoet inneholder allerede en nedlastet DEM, sa denne leveransen bruker den eksisterende filen:

```powershell
$DEM = 'Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM\6404_1_10m_z32.dem'
```

Kontroll av inputdata:

```powershell
& 'C:\Program Files\QGIS 3.40.15\bin\gdalinfo.exe' $DEM
```

Viktige egenskaper fra `gdalinfo`:

- Rasterstorrelse: `5041 x 5041`
- Pikselstorrelse: `10 x 10 meter`
- Koordinatsystem: `WGS 84 / UTM zone 32N (EPSG:32632)`
- Hoydeenhet: `meter`

## 3. Helningskart og filter > 30 grader

Oppsett:

```powershell
$QGIS_BIN = 'C:\Program Files\QGIS 3.40.15\bin'
$QGIS_SCRIPTS = 'C:\Program Files\QGIS 3.40.15\apps\Python312\Scripts'
$OUT = 'raster-output'
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
```

Lag helningskart i grader:

```powershell
& "$QGIS_BIN\gdaldem.exe" slope `
  $DEM `
  "$OUT\slope_degrees.tif" `
  -of GTiff `
  -compute_edges
```

Filtrer ut celler med helning storre enn 30 grader:

```powershell
& "$QGIS_SCRIPTS\gdal_calc.exe" `
  -A "$OUT\slope_degrees.tif" `
  --outfile "$OUT\slope_gt_30_mask.tif" `
  --calc "1*(A>30)" `
  --type Byte `
  --NoDataValue 0 `
  --format GTiff `
  --overwrite
```

## 4. Polygonize til vektordata

Polygoniser masken:

```powershell
& "$QGIS_SCRIPTS\gdal_polygonize.exe" `
  "$OUT\slope_gt_30_mask.tif" `
  -f GPKG `
  "$OUT\slope_gt_30_polygons.gpkg" `
  steep_areas `
  gt30 `
  -overwrite
```

Behold bare polygoner der `gt30 = 1`:

```powershell
& "$QGIS_BIN\ogr2ogr.exe" `
  -f GPKG `
  "$OUT\slope_gt_30_only.gpkg" `
  "$OUT\slope_gt_30_polygons.gpkg" `
  steep_areas `
  -where "gt30 = 1"
```

## 5. To hillshade-varianter

Hillshade 1, klassisk belysning:

```powershell
& "$QGIS_BIN\gdaldem.exe" hillshade `
  $DEM `
  "$OUT\hillshade_315_45.tif" `
  -of GTiff `
  -az 315 `
  -alt 45 `
  -compute_edges
```

Hillshade 2, endret retning, lavere solvinkel og sterkere vertikal effekt:

```powershell
& "$QGIS_BIN\gdaldem.exe" hillshade `
  $DEM `
  "$OUT\hillshade_225_30_z2.tif" `
  -of GTiff `
  -az 225 `
  -alt 30 `
  -z 2 `
  -compute_edges
```

## 6. Verifisering

Statistikk for helningskart:

```powershell
& "$QGIS_BIN\gdalinfo.exe" -stats "$OUT\slope_degrees.tif"
```

Resultat:

- Minimum helning: `0`
- Maksimum helning: `73.73`
- Gjennomsnittlig helning: `7.45`

Kontroll av vektorresultat:

```powershell
& "$QGIS_BIN\ogrinfo.exe" -so "$OUT\slope_gt_30_only.gpkg" steep_areas
& "$QGIS_BIN\ogrinfo.exe" "$OUT\slope_gt_30_only.gpkg" -dialect SQLite -sql "SELECT COUNT(*) AS feature_count, ROUND(SUM(ST_Area(geom))/1000000.0, 2) AS area_km2 FROM steep_areas"
```

Resultat:

- Antall polygoner med helning > 30 grader: `39707`
- Samlet areal: `73.93 km2`

Genererte filer:

- `raster-output/slope_degrees.tif`
- `raster-output/slope_gt_30_mask.tif`
- `raster-output/slope_gt_30_polygons.gpkg`
- `raster-output/slope_gt_30_only.gpkg`
- `raster-output/hillshade_315_45.tif`
- `raster-output/hillshade_225_30_z2.tif`
