"""
ASCII Raman spectrum reader.

This module reads two-column Raman spectrum files and converts them
into the standard spectral-data dictionary used throughout FAIRaman.
"""

from pathlib import Path
import numpy as np
import pandas as pd
from fairaman.readers import wdf_reader, ascii_reader
from fairaman.constant import COORDINATE_MODE_REGULAR, COORDINATE_MODE_POINTS

SUPPORTED_DELIMITERS = (None, ",", ";")

def process_txt_spectrum(txt_path: Path) -> dict:
    """
    Importer ASCII/CSV → dizionario canonico FAIRaman.

    Formati supportati
    ------------------
    1) Spettro singolo:
       raman_shift | intensity

       Output:
       regular_grid 1×1
       cube shape = (1, 1, n_wavenumbers)
       x_axis = [0.0], y_axis = [0.0]
       coordinate_source = "synthetic"
       coordinate_units = "micrometers"
       coordinate_validated = False

    2) Matrice multi-spettro senza coordinate:
       raman_shift | spectrum_1 | spectrum_2 | ... | spectrum_n

       Output:
       regular_grid 1×n
       cube shape = (1, n_spectra, n_wavenumbers)
       x_axis = [0.0, 1.0, 2.0, ...]
       y_axis = [0.0]
       coordinate_source = "synthetic"
       coordinate_units = "micrometers"
       coordinate_validated = False

    3) Formato spaziale long:
       x | y | raman_shift | intensity

       Ogni riga rappresenta un singolo valore spettrale in una posizione (x, y).
       FAIRaman ricostruisce uno spettro per ogni coppia x/y.

    4) Formato spaziale wide con header:
       x | y | 800 | 801 | 802 | ...

       Le colonne dalla terza in poi sono intensità Raman; gli header numerici
       sono i Raman shift.

    Convenzione FAIRaman
    --------------------
    Tutte le coordinate x/y sono espresse in micrometri.

    Se il file non contiene coordinate fisiche, FAIRaman genera coordinate
    sintetiche in micrometri solo per mantenere una struttura HDF5 compatibile.
    In questi casi:
       coordinate_source = "synthetic"
       coordinate_validated = False
    """

    def _base_output() -> dict:
        """Crea il dizionario canonico base per un importer ASCII/CSV."""
        instrument_meta = {
            "laser_wavelength": 0.0,
            "x_start": 0.0,
            "y_start": 0.0,
            "x_step": 0.0,
            "y_step": 0.0,
        }

        out = wdf_reader._canonical_defaults()
        out.update({
            "cube":             None,
            "spectra":          None,
            "raman_shift":      None,
            "x_axis":           None,
            "y_axis":           None,
            "x":                None,
            "y":                None,
            "white_light":      None,
            "white_light_meta": None,
            "acquisition_map":  None,
            "instrument":       instrument_meta,
            "filename":         txt_path.name,
            "source_format":    "txt",
        })
        return out

    def _read_ascii_table(path: Path) -> pd.DataFrame:
        """
        Legge una tabella ASCII/CSV provando delimitatori comuni.
        Usa header=None per poter riconoscere anche header numerici dei Raman shift.
        """
        for sep in [r"\s+", ",", ";", "\t"]:
            try:
                df = pd.read_csv(
                    path,
                    comment="#",
                    sep=sep,
                    header=None,
                    engine="python",
                )
                df = df.dropna(how="all").dropna(axis=1, how="all")

                if df.shape[0] > 0 and df.shape[1] >= 2:
                    return df

            except Exception:
                continue

        raise ValueError(
            f"Could not parse '{path.name}': no supported delimiter found "
            f"(tried whitespace, comma, semicolon, tab)."
        )

    def _sort_by_raman_shift(
        raman_shift: np.ndarray,
        spectra: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Ordina l'asse Raman in ordine crescente.

        Parameters
        ----------
        raman_shift
            Array shape = (n_wavenumbers,)
        spectra
            Array shape = (n_spectra, n_wavenumbers)
        """
        raman_shift = np.asarray(raman_shift, dtype=np.float64)
        spectra = np.asarray(spectra, dtype=np.float64)

        if spectra.ndim != 2:
            raise ValueError(f"spectra must be 2D, detected shape {spectra.shape}")

        if spectra.shape[1] != len(raman_shift):
            raise ValueError(
                f"spectra second dimension must match raman_shift length "
                f"({spectra.shape[1]} != {len(raman_shift)})"
            )

        sort_idx = np.argsort(raman_shift)
        return raman_shift[sort_idx], spectra[:, sort_idx]

    def _as_regular_grid_from_axes(
        raman_shift: np.ndarray,
        cube: np.ndarray,
        x_axis: np.ndarray,
        y_axis: np.ndarray,
        coordinate_source: str,
        coordinate_validated: bool,
        reshape_applied: bool,
        reshape_source: str,
    ) -> dict:
        """
        Costruisce un output canonico regular_grid.
        """
        out = _base_output()

        out.update({
            "cube":                 np.asarray(cube, dtype=np.float64),
            "spectra":              None,
            "raman_shift":          np.asarray(raman_shift, dtype=np.float64),
            "x_axis":               np.asarray(x_axis, dtype=np.float64),
            "y_axis":               np.asarray(y_axis, dtype=np.float64),
            "x":                    None,
            "y":                    None,
            "coordinate_mode":      COORDINATE_MODE_REGULAR,
            "coordinate_source":    coordinate_source,
            "coordinate_units":     "micrometers",
            "coordinate_validated": bool(coordinate_validated),
            "reshape_applied":      bool(reshape_applied),
            "reshape_source":       reshape_source,
        })

        return out

    def _as_points(
        raman_shift: np.ndarray,
        spectra: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        coordinate_source: str,
        coordinate_validated: bool,
    ) -> dict:
        """
        Costruisce un output canonico point_coordinates.
        Usato solo quando x/y reali non formano una griglia completa.
        """
        out = _base_output()

        out.update({
            "cube":                 None,
            "spectra":              np.asarray(spectra, dtype=np.float64),
            "raman_shift":          np.asarray(raman_shift, dtype=np.float64),
            "x_axis":               None,
            "y_axis":               None,
            "x":                    np.asarray(x, dtype=np.float64),
            "y":                    np.asarray(y, dtype=np.float64),
            "coordinate_mode":      COORDINATE_MODE_POINTS,
            "coordinate_source":    coordinate_source,
            "coordinate_units":     "micrometers",
            "coordinate_validated": bool(coordinate_validated),
            "reshape_applied":      False,
            "reshape_source":       "none",
        })

        return out

    def _grid_or_points_from_xy(
        raman_shift: np.ndarray,
        spectra: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        coordinate_source: str,
    ) -> dict:
        """
        Decide se coordinate x/y rappresentano una griglia completa o punti sparsi.

        Se tutte le combinazioni x_unique × y_unique sono presenti una sola volta,
        il dato viene salvato come regular_grid.

        Altrimenti viene salvato come point_coordinates, conservando x/y per-spettro.
        """
        raman_shift = np.asarray(raman_shift, dtype=np.float64)
        spectra = np.asarray(spectra, dtype=np.float64)
        x = np.asarray(x, dtype=np.float64).ravel()
        y = np.asarray(y, dtype=np.float64).ravel()

        if spectra.ndim != 2:
            raise ValueError(f"spectra must be 2D, detected shape {spectra.shape}")

        n_points, n_wavenumbers = spectra.shape

        if len(raman_shift) != n_wavenumbers:
            raise ValueError(
                f"len(raman_shift) != spectra.shape[1] "
                f"({len(raman_shift)} != {n_wavenumbers})"
            )

        if x.size != n_points or y.size != n_points:
            raise ValueError(
                f"x/y coordinates do not match spectra count: "
                f"len(x)={x.size}, len(y)={y.size}, n_spectra={n_points}"
            )

        coord_df = pd.DataFrame({
            "x": x,
            "y": y,
            "idx": np.arange(n_points),
        })

        if coord_df.duplicated(["x", "y"]).any():
            duplicated = coord_df[coord_df.duplicated(["x", "y"], keep=False)]
            raise ValueError(
                f"Duplicate x/y coordinates found in '{txt_path.name}'. "
                f"Duplicated rows: {duplicated[['x', 'y']].head().to_dict('records')}"
            )

        x_unique = np.sort(np.unique(x))
        y_unique = np.sort(np.unique(y))

        is_complete_grid = (
            len(x_unique) > 1
            and len(y_unique) > 1
            and len(x_unique) * len(y_unique) == n_points
        )

        if is_complete_grid:
            complete_index = pd.MultiIndex.from_product(
                [y_unique, x_unique],
                names=["y", "x"],
            )

            ordered = (
                coord_df
                .set_index(["y", "x"])
                .reindex(complete_index)
            )

            if not ordered["idx"].isna().any():
                order = ordered["idx"].astype(int).to_numpy()

                cube = spectra[order, :].reshape(
                    len(y_unique),
                    len(x_unique),
                    len(raman_shift),
                )

                return _as_regular_grid_from_axes(
                    raman_shift=raman_shift,
                    cube=cube,
                    x_axis=x_unique,
                    y_axis=y_unique,
                    coordinate_source=coordinate_source,
                    coordinate_validated=True,
                    reshape_applied=True,
                    reshape_source="ASCII x/y grid",
                )

        return _as_points(
            raman_shift=raman_shift,
            spectra=spectra,
            x=x,
            y=y,
            coordinate_source=coordinate_source,
            coordinate_validated=True,
        )

    # ── Lettura tabella ───────────────────────────────────────────────────────
    df_raw = _read_ascii_table(txt_path)
    df_num = df_raw.apply(pd.to_numeric, errors="coerce")

    # ── CASE 4: wide spatial format con header ────────────────────────────────
    # Esempio:
    #   x,y,800,801,802
    #   0,0,10,11,12
    #   1,0,13,14,15
    #
    # Con header=None + to_numeric:
    #   prima riga = NaN, NaN, 800, 801, 802
    if df_num.shape[0] >= 2 and df_num.shape[1] >= 4:
        first_row = df_num.iloc[0, :]

        looks_like_wide_spatial_header = (
            pd.isna(first_row.iloc[0])
            and pd.isna(first_row.iloc[1])
            and first_row.iloc[2:].notna().all()
        )

        if looks_like_wide_spatial_header:
            raman_shift = first_row.iloc[2:].to_numpy(dtype=np.float64)
            body = df_num.iloc[1:, :].dropna(how="all")

            if body.isna().any().any():
                raise ValueError(
                    f"'{txt_path.name}' looks like wide spatial ASCII/CSV with "
                    f"header, but some numeric values are missing."
                )

            x = body.iloc[:, 0].to_numpy(dtype=np.float64)
            y = body.iloc[:, 1].to_numpy(dtype=np.float64)
            spectra = body.iloc[:, 2:].to_numpy(dtype=np.float64)

            raman_shift, spectra = _sort_by_raman_shift(raman_shift, spectra)

            return _grid_or_points_from_xy(
                raman_shift=raman_shift,
                spectra=spectra,
                x=x,
                y=y,
                coordinate_source="ASCII x/y columns + Raman-shift header",
            )

    # Da qui in avanti usiamo solo righe completamente numeriche.
    df_clean = df_num.dropna(how="all").dropna(axis=0, how="any")

    if df_clean.empty:
        raise ValueError(
            f"'{txt_path.name}' does not contain a usable numeric table."
        )

    arr = df_clean.to_numpy(dtype=np.float64)

    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError(
            f"'{txt_path.name}' must contain at least two numeric columns. "
            f"Detected shape: {arr.shape}."
        )

    # ── CASE 3: long spatial format x | y | raman_shift | intensity ───────────
    # Esempio:
    #   x,y,raman_shift,intensity
    #   0,0,800,10
    #   0,0,801,11
    #   1,0,800,13
    #   1,0,801,14
    if arr.shape[1] >= 4:
        x_col = arr[:, 0]
        y_col = arr[:, 1]
        wn_col = arr[:, 2]
        intensity_col = arr[:, 3]

        point_df = pd.DataFrame({"x": x_col, "y": y_col})
        n_points = point_df.drop_duplicates().shape[0]
        n_wavenumbers = np.unique(wn_col).size

        looks_like_long_spatial = (
            n_points > 1
            and n_wavenumbers > 1
            and n_points * n_wavenumbers == arr.shape[0]
        )

        if looks_like_long_spatial:
            long_df = pd.DataFrame({
                "x": x_col,
                "y": y_col,
                "raman_shift": wn_col,
                "intensity": intensity_col,
            })

            if long_df.duplicated(["x", "y", "raman_shift"]).any():
                duplicated = long_df[
                    long_df.duplicated(["x", "y", "raman_shift"], keep=False)
                ]
                raise ValueError(
                    f"Duplicate x/y/raman_shift rows found in '{txt_path.name}'. "
                    f"Duplicated rows: "
                    f"{duplicated[['x', 'y', 'raman_shift']].head().to_dict('records')}"
                )

            pivot = long_df.pivot(
                index=["y", "x"],
                columns="raman_shift",
                values="intensity",
            )

            pivot = pivot.reindex(sorted(pivot.columns), axis=1)

            if pivot.isna().any().any():
                raise ValueError(
                    f"'{txt_path.name}' looks like long spatial ASCII/CSV "
                    f"(x, y, raman_shift, intensity), but the x/y × Raman grid "
                    f"is incomplete."
                )

            raman_shift = pivot.columns.to_numpy(dtype=np.float64)
            spectra = pivot.to_numpy(dtype=np.float64)
            y = pivot.index.get_level_values("y").to_numpy(dtype=np.float64)
            x = pivot.index.get_level_values("x").to_numpy(dtype=np.float64)

            raman_shift, spectra = _sort_by_raman_shift(raman_shift, spectra)

            return _grid_or_points_from_xy(
                raman_shift=raman_shift,
                spectra=spectra,
                x=x,
                y=y,
                coordinate_source="ASCII x/y/raman_shift/intensity columns",
            )

    # ── CASE 1: single spectrum raman_shift | intensity ───────────────────────
    if arr.shape[1] == 2:
        raman_shift = arr[:, 0].astype(np.float64)
        intensity = arr[:, 1].astype(np.float64).reshape(1, -1)

        raman_shift, spectra = _sort_by_raman_shift(raman_shift, intensity)

        cube = spectra.reshape(1, 1, -1)

        return _as_regular_grid_from_axes(
            raman_shift=raman_shift,
            cube=cube,
            x_axis=np.array([0.0]),
            y_axis=np.array([0.0]),
            coordinate_source="synthetic",
            coordinate_validated=False,
            reshape_applied=True,
            reshape_source="ASCII single spectrum as 1x1 map",
        )

    # ── CASE 2: matrix raman_shift | spectrum_1 | spectrum_2 | ... ────────────
    # Esempio:
    #   800  10  11  15
    #   801  12  13  16
    #   802  14  15  18
    #
    # Nessuna coordinata reale: salviamo come mappa sintetica 1×n.
    raman_shift = arr[:, 0].astype(np.float64)
    spectra = arr[:, 1:].T.astype(np.float64)

    raman_shift, spectra = _sort_by_raman_shift(raman_shift, spectra)

    n_spectra = spectra.shape[0]
    cube = spectra.reshape(1, n_spectra, -1)

    return _as_regular_grid_from_axes(
        raman_shift=raman_shift,
        cube=cube,
        x_axis=np.arange(n_spectra, dtype=float),
        y_axis=np.array([0.0]),
        coordinate_source="synthetic",
        coordinate_validated=False,
        reshape_applied=True,
        reshape_source="ASCII matrix as 1xn map",
    )
