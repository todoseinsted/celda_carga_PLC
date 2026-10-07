#!/usr/bin/env python3
"""Lectura segura del peso del volquete en un Raspberry PLC 19R V6.

Cadena de medicion esperada:
    4 celdas -> caja sumadora -> DY500 (4-20 mA)
    -> Weidmuller ACT20M (4-20 mA a 0-10 V) -> I0.5

El programa es solo de lectura: no configura ni acciona salidas del PLC.
Permite una calibracion de dos puntos en campo:
    1. Volquete vacio: --hacer-cero
    2. Peso conocido: --calibrar-peso KG
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ADC_MAX = 4095
ADC_RANGE_V = 10.0
CURRENT_MIN_MA = 4.0
CURRENT_SPAN_MA = 16.0
DEFAULT_CHANNEL = "I0.5"
DEFAULT_FULL_SCALE_KG = 20_000.0
DEFAULT_DRIVER = "/home/RaspPLC1/test/RPIPLC_V6/RPIPLC_19R/get-analog-input"
DEFAULT_CONFIG = "/home/RaspPLC1/Ensayos/peso_calibracion.json"
VALID_CHANNELS = ("I0.2", "I0.3", "I0.4", "I0.5")


@dataclass
class Calibration:
    zero_raw: float
    span_raw: float | None = None
    span_kg: float | None = None
    updated_at: str = ""

    @property
    def complete(self) -> bool:
        return (
            self.span_raw is not None
            and self.span_kg is not None
            and self.span_kg > 0
            and self.span_raw > self.zero_raw
        )


@dataclass(frozen=True)
class Measurement:
    timestamp: str
    channel: str
    raw: float
    voltage_v: float
    current_ma: float
    weight_kg: float
    status: str
    calibrated: bool


def read_raw_once(driver: str, channel: str) -> int:
    result = subprocess.run(
        [driver, channel],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not value.isdigit():
        detail = result.stderr.strip() or value or f"codigo {result.returncode}"
        raise RuntimeError(f"no se pudo leer {channel}: {detail}")
    raw = int(value)
    if not 0 <= raw <= ADC_MAX:
        raise RuntimeError(f"lectura ADC fuera de rango: {raw}")
    return raw


def read_filtered(driver: str, channel: str, samples: int, delay_s: float) -> float:
    values: list[int] = []
    for index in range(samples):
        values.append(read_raw_once(driver, channel))
        if index + 1 < samples:
            time.sleep(delay_s)
    return float(statistics.median(values))


def load_calibration(path: Path) -> Calibration | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    calibration = Calibration(
        zero_raw=float(data["zero_raw"]),
        span_raw=float(data["span_raw"]) if data.get("span_raw") is not None else None,
        span_kg=float(data["span_kg"]) if data.get("span_kg") is not None else None,
        updated_at=str(data.get("updated_at", "")),
    )
    if not 0 <= calibration.zero_raw <= ADC_MAX:
        raise ValueError("zero_raw invalido en el archivo de calibracion")
    if calibration.span_raw is not None and not 0 <= calibration.span_raw <= ADC_MAX:
        raise ValueError("span_raw invalido en el archivo de calibracion")
    if calibration.span_kg is not None and calibration.span_kg <= 0:
        raise ValueError("span_kg debe ser positivo")
    return calibration


def save_calibration(path: Path, calibration: Calibration) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    calibration.updated_at = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(calibration), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def convert(
    raw: float,
    channel: str,
    calibration: Calibration | None,
    nominal_full_scale_kg: float,
    allow_negative: bool,
) -> Measurement:
    voltage = raw * ADC_RANGE_V / ADC_MAX
    current = CURRENT_MIN_MA + CURRENT_SPAN_MA * voltage / ADC_RANGE_V

    if calibration is not None and calibration.complete:
        assert calibration.span_raw is not None
        assert calibration.span_kg is not None
        weight = (raw - calibration.zero_raw) * calibration.span_kg / (
            calibration.span_raw - calibration.zero_raw
        )
        calibrated = True
        status = "OK_CALIBRADO"
    else:
        zero_raw = calibration.zero_raw if calibration is not None else 0.0
        usable_span = ADC_MAX - zero_raw
        weight = (raw - zero_raw) * nominal_full_scale_kg / usable_span
        calibrated = False
        status = "ESTIMADO_FALTA_CALIBRACION_CON_PESO"

    if raw >= ADC_MAX - 3:
        status = "SATURACION_ALTA"
    elif calibration is not None and raw < calibration.zero_raw - 10:
        status = "POR_DEBAJO_DEL_CERO"

    if not allow_negative:
        weight = max(0.0, weight)

    return Measurement(
        timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
        channel=channel,
        raw=round(raw, 2),
        voltage_v=round(voltage, 4),
        current_ma=round(current, 4),
        weight_kg=round(weight, 1),
        status=status,
        calibrated=calibrated,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lee el peso del volquete desde I0.5 sin accionar salidas."
    )
    parser.add_argument("--channel", choices=VALID_CHANNELS, default=DEFAULT_CHANNEL)
    parser.add_argument("--driver", default=DEFAULT_DRIVER)
    parser.add_argument("--config", type=Path, default=Path(DEFAULT_CONFIG))
    parser.add_argument("--samples", type=int, default=11)
    parser.add_argument("--sample-delay", type=float, default=0.03)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--full-scale-kg", type=float, default=DEFAULT_FULL_SCALE_KG)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-negative", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--hacer-cero",
        action="store_true",
        help="guarda la lectura actual como cero; usar solo con el volquete vacio y estable",
    )
    action.add_argument(
        "--calibrar-peso",
        type=float,
        metavar="KG",
        help="guarda el segundo punto con un peso conocido",
    )
    action.add_argument("--mostrar-config", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.samples < 3 or args.samples % 2 == 0:
        raise ValueError("--samples debe ser impar y al menos 3")
    if args.sample_delay < 0 or args.interval <= 0:
        raise ValueError("los intervalos deben ser positivos")
    if args.full_scale_kg <= 0:
        raise ValueError("--full-scale-kg debe ser positivo")
    if args.calibrar_peso is not None and args.calibrar_peso <= 0:
        raise ValueError("--calibrar-peso debe ser mayor que cero")


def print_measurement(measurement: Measurement, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(measurement), ensure_ascii=False), flush=True)
        return
    calibration_label = "calibrado" if measurement.calibrated else "estimado"
    print(
        f"{measurement.timestamp} | {measurement.channel} | "
        f"raw={measurement.raw:7.2f} | {measurement.voltage_v:6.3f} V | "
        f"equiv={measurement.current_ma:6.3f} mA | "
        f"peso={measurement.weight_kg:9.1f} kg ({calibration_label}) | "
        f"{measurement.status}",
        flush=True,
    )


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        calibration = load_calibration(args.config)

        if args.mostrar_config:
            if calibration is None:
                print("No existe calibracion guardada.")
                return 1
            print(json.dumps(asdict(calibration), ensure_ascii=False, indent=2))
            return 0

        if args.hacer_cero:
            raw = read_filtered(args.driver, args.channel, args.samples, args.sample_delay)
            # Un nuevo cero invalida el segundo punto anterior para evitar usar una
            # pendiente que ya no corresponde a la instalacion mecanica actual.
            calibration = Calibration(zero_raw=raw)
            save_calibration(args.config, calibration)
            print(f"Cero guardado: raw={raw:.2f}. Falta calibrar con un peso conocido.")
            return 0

        if args.calibrar_peso is not None:
            if calibration is None:
                raise ValueError("primero ejecute --hacer-cero con el volquete vacio")
            raw = read_filtered(args.driver, args.channel, args.samples, args.sample_delay)
            if raw <= calibration.zero_raw + 5:
                raise ValueError(
                    "la senal con carga es demasiado cercana al cero; revise cableado o use mas peso"
                )
            calibration.span_raw = raw
            calibration.span_kg = args.calibrar_peso
            save_calibration(args.config, calibration)
            print(
                f"Calibracion guardada: cero={calibration.zero_raw:.2f}, "
                f"punto={raw:.2f} para {args.calibrar_peso:.1f} kg."
            )
            return 0

        while True:
            raw = read_filtered(args.driver, args.channel, args.samples, args.sample_delay)
            measurement = convert(
                raw,
                args.channel,
                calibration,
                args.full_scale_kg,
                args.allow_negative,
            )
            print_measurement(measurement, args.json)
            if args.once:
                return 0
            time.sleep(args.interval)

    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


