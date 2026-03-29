from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape


DEFAULT_DEM = Path("Basisdata_6404-1_Celle_25832_DTM10UTM32_DEM/6404_1_10m_z32.dem")
DEFAULT_OUTPUT_DIR = Path("outputs/rasteranalyse")
DEFAULT_THRESHOLD = 30.0


@dataclass(frozen=True)
class HillshadeSpec:
    name: str
    azimuth: float
    altitude: float
    z_factor: float


DEFAULT_HILLSHADES = (
    HillshadeSpec("hillshade_standard", azimuth=315.0, altitude=45.0, z_factor=1.0),
    HillshadeSpec("hillshade_dramatic", azimuth=225.0, altitude=30.0, z_factor=1.6),
)


def parse_hillshade_spec(raw_value: str) -> HillshadeSpec:
    parts = [part.strip() for part in raw_value.split(":")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "Hillshade must use NAME:AZIMUTH:ALTITUDE:ZFACTOR format."
        )

    name, azimuth, altitude, z_factor = parts
    try:
        return HillshadeSpec(
            name=name,
            azimuth=float(azimuth),
            altitude=float(altitude),
            z_factor=float(z_factor),
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Azimuth, altitude and z-factor must be numeric values."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create slope, steep-area mask, polygonized steep areas and hillshades from a DEM."
    )
    parser.add_argument(
        "--dem",
        type=Path,
        default=DEFAULT_DEM,
        help=f"Path to input DEM. Defaults to {DEFAULT_DEM}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for generated outputs. Defaults to {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--slope-threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Slope threshold in degrees. Defaults to {DEFAULT_THRESHOLD}.",
    )
    parser.add_argument(
        "--hillshade",
        action="append",
        type=parse_hillshade_spec,
        help="Optional hillshade spec in NAME:AZIMUTH:ALTITUDE:ZFACTOR format. Can be repeated.",
    )
    return parser.parse_args()


def load_dem(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    with rasterio.open(path) as src:
        dem = src.read(1, masked=True).astype("float64")
        meta = src.profile.copy()
        meta["crs"] = src.crs
        meta["transform"] = src.transform
        meta["bounds"] = src.bounds
        meta["xres"] = src.transform.a
        meta["yres"] = abs(src.transform.e)
        return dem.filled(np.nan), ~dem.mask, meta


def gradients(
    dem: np.ndarray, xres: float, yres: float, z_factor: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    scaled = dem * z_factor
    dz_dy, dz_dx = np.gradient(scaled, yres, xres)
    return dz_dx, dz_dy


def compute_slope_degrees(
    dem: np.ndarray, valid_mask: np.ndarray, xres: float, yres: float
) -> np.ndarray:
    dz_dx, dz_dy = gradients(dem, xres=xres, yres=yres)
    slope_radians = np.arctan(np.sqrt((dz_dx**2) + (dz_dy**2)))
    slope_degrees = np.degrees(slope_radians)
    slope_degrees[~valid_mask] = np.nan
    return slope_degrees.astype("float32")


def compute_hillshade(
    dem: np.ndarray,
    valid_mask: np.ndarray,
    xres: float,
    yres: float,
    azimuth: float,
    altitude: float,
    z_factor: float,
) -> np.ndarray:
    dz_dx, dz_dy = gradients(dem, xres=xres, yres=yres, z_factor=z_factor)
    slope = np.arctan(np.sqrt((dz_dx**2) + (dz_dy**2)))
    aspect = np.arctan2(dz_dy, -dz_dx)

    azimuth_math = 360.0 - azimuth + 90.0
    if azimuth_math >= 360.0:
        azimuth_math -= 360.0

    azimuth_radians = np.radians(azimuth_math)
    altitude_radians = np.radians(altitude)

    shaded = (
        np.sin(altitude_radians) * np.sin(slope)
        + np.cos(altitude_radians) * np.cos(slope) * np.cos(azimuth_radians - aspect)
    )
    hillshade = np.clip(shaded, 0.0, 1.0) * 255.0
    hillshade[~valid_mask] = np.nan
    return hillshade.astype("float32")


def write_raster(
    path: Path, array: np.ndarray, meta: dict, dtype: str, nodata: float | int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = meta.copy()
    for key in ("bounds", "xres", "yres"):
        profile.pop(key, None)
    profile.update(
        driver="GTiff",
        count=1,
        dtype=dtype,
        nodata=nodata,
        compress="deflate",
    )

    output = np.where(np.isfinite(array), array, nodata).astype(dtype)

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(output, 1)


def build_steep_mask(
    slope_degrees: np.ndarray, valid_mask: np.ndarray, threshold: float
) -> np.ndarray:
    mask = np.full(slope_degrees.shape, 255, dtype="uint8")
    mask[valid_mask] = 0
    mask[valid_mask & (slope_degrees > threshold)] = 1
    return mask


def polygonize_mask(
    mask: np.ndarray,
    transform,
    crs,
    geojson_path: Path,
    gpkg_path: Path | None = None,
) -> int:
    polygons = []
    for geometry, value in shapes(mask, mask=mask == 1, transform=transform):
        if int(value) != 1:
            continue
        polygons.append(shape(geometry))

    gdf = gpd.GeoDataFrame(
        {"steep": [1] * len(polygons)},
        geometry=polygons,
        crs=crs,
    )
    if not gdf.empty and crs and crs.is_projected:
        gdf["area_m2"] = gdf.area
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(geojson_path, driver="GeoJSON")
    if gpkg_path is not None:
        gpkg_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(gpkg_path, driver="GPKG", layer=gpkg_path.stem)
    return len(gdf)


def main() -> None:
    args = parse_args()
    dem_path = args.dem
    output_dir = args.output_dir
    hillshades = tuple(args.hillshade) if args.hillshade else DEFAULT_HILLSHADES

    dem, valid_mask, meta = load_dem(dem_path)
    slope_degrees = compute_slope_degrees(
        dem,
        valid_mask=valid_mask,
        xres=meta["xres"],
        yres=meta["yres"],
    )

    slope_path = output_dir / "slope_degrees.tif"
    write_raster(slope_path, slope_degrees, meta=meta, dtype="float32", nodata=-9999.0)

    steep_mask = build_steep_mask(
        slope_degrees,
        valid_mask=valid_mask,
        threshold=args.slope_threshold,
    )
    threshold_label = f"{args.slope_threshold:g}".replace(".", "_")
    steep_mask_path = output_dir / f"steep_gt_{threshold_label}deg.tif"
    write_raster(
        steep_mask_path,
        steep_mask.astype("float32"),
        meta=meta,
        dtype="uint8",
        nodata=255,
    )

    polygons_geojson_path = output_dir / f"steep_gt_{threshold_label}deg.geojson"
    polygons_gpkg_path = output_dir / f"steep_gt_{threshold_label}deg.gpkg"
    polygon_count = polygonize_mask(
        steep_mask,
        transform=meta["transform"],
        crs=meta["crs"],
        geojson_path=polygons_geojson_path,
        gpkg_path=polygons_gpkg_path,
    )

    print(f"DEM: {dem_path}")
    print(f"Slope raster: {slope_path}")
    print(f"Steep mask raster: {steep_mask_path}")
    print(
        "Steep polygons:"
        f" {polygons_geojson_path}"
        f" and {polygons_gpkg_path}"
        f" ({polygon_count} polygons)"
    )

    for spec in hillshades:
        hillshade = compute_hillshade(
            dem,
            valid_mask=valid_mask,
            xres=meta["xres"],
            yres=meta["yres"],
            azimuth=spec.azimuth,
            altitude=spec.altitude,
            z_factor=spec.z_factor,
        )
        hillshade_path = (
            output_dir
            / f"{spec.name}_az{int(spec.azimuth)}_alt{int(spec.altitude)}_z{spec.z_factor:.1f}.tif"
        )
        write_raster(
            hillshade_path, hillshade, meta=meta, dtype="float32", nodata=-9999.0
        )
        print(
            "Hillshade:"
            f" {hillshade_path}"
            f" (azimuth={spec.azimuth}, altitude={spec.altitude}, z_factor={spec.z_factor})"
        )


if __name__ == "__main__":
    main()
