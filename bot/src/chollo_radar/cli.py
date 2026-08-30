from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .config import AppConfig, load_config, load_dotenv
from .pipeline import run_once
from .providers import AmazonCreatorsProvider, DemoProvider
from .publishers import ConsolePublisher, TelegramPublisher
from .storage import create_storage


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chollo Radar Bot")
    parser.add_argument(
        "command",
        choices={"once", "run", "status", "test-telegram", "check-config"},
    )
    parser.add_argument("--config", default="config.json")
    return parser


def _provider(config: AppConfig):
    if config.source == "demo":
        return DemoProvider(config.demo_feed_path)
    return AmazonCreatorsProvider.from_env()


def _telegram() -> TelegramPublisher:
    return TelegramPublisher(
        os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        os.getenv("TELEGRAM_CHAT_ID", "").strip(),
    )


def _publisher(config: AppConfig):
    return ConsolePublisher() if config.dry_run else _telegram()


def _print_summary(summary) -> None:
    print(
        "Resumen: "
        f"búsquedas={summary.queries}, obtenidas={summary.fetched}, "
        f"válidas={summary.eligible}, publicadas={summary.published}, "
        f"previsualizadas={summary.previewed}, "
        f"repetidas={summary.skipped_recent}"
    )
    for error in summary.errors:
        print(f"ERROR: {error}", file=sys.stderr)


def _run_cycle(config: AppConfig) -> int:
    if config.source == "demo" and not config.dry_run:
        raise ValueError(
            "El feed demo no se puede publicar. Usa DRY_RUN=true o configura "
            "BOT_SOURCE=amazon."
        )
    storage = create_storage(config.database_path)
    run_id = ""
    try:
        run_id = storage.start_run(config.source, config.dry_run)
        summary = run_once(config, _provider(config), _publisher(config), storage)
        storage.finish_run(run_id, summary)
        _print_summary(summary)
        critical_prefixes = (
            "persistencia ",
            "deduplicación ",
            "registro publicación ",
        )
        critical = bool(summary.errors and summary.fetched == 0) or any(
            error.startswith(critical_prefixes) for error in summary.errors
        )
        return 1 if critical else 0
    except Exception as exc:
        try:
            storage.finish_run(run_id, None, str(exc))
        except Exception as log_exc:
            print(f"ERROR al registrar la ejecución: {log_exc}", file=sys.stderr)
        raise
    finally:
        storage.close()


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parser().parse_args(argv)
    try:
        config = load_config(Path(args.config))
        if args.command == "check-config":
            _provider(config)
            if not config.dry_run:
                _publisher(config)
            storage = create_storage(config.database_path)
            try:
                storage.get_cursor()
            finally:
                storage.close()
            print(
                f"Configuración válida: fuente={config.source}, "
                f"dry_run={config.dry_run}, búsquedas={len(config.queries)}"
            )
            return 0
        if args.command == "test-telegram":
            _telegram().send_test()
            print("Mensaje de prueba enviado.")
            return 0
        if args.command == "status":
            storage = create_storage(config.database_path)
            try:
                print(json.dumps(storage.stats(), indent=2, ensure_ascii=False))
            finally:
                storage.close()
            return 0
        if args.command == "once":
            return _run_cycle(config)

        print(
            f"Bot iniciado: un ciclo cada {config.interval_minutes} minutos. "
            "Pulsa Ctrl+C para detenerlo."
        )
        while True:
            _run_cycle(config)
            time.sleep(config.interval_minutes * 60)
    except KeyboardInterrupt:
        print("Bot detenido.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
