"""Lê aparelhos físicos e consumo, sem alterar relés nem ajustes do Elgin.

Não imprime credenciais, IPs, IDs ou respostas brutas de transporte.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'src'))
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from elgin_app import ElginApp
from ekaza_plug import run_operation, medidas, ler_config
from bridge import EnergyBridge
from energy_history import local_now


def check_ac():
    dps, error = ElginApp.run_operation('status', None)
    if error or not dps:
        return {'connected': False, 'error': 'Elgin sem resposta LAN válida; confira configuração e rede.'}
    return {'connected': True, 'power': dps.get('1'), 'ambient_c': dps.get('3'),
            'setpoint_c': dps.get('2'), 'mode': dps.get('4'), 'fan': dps.get('5')}


def check_plug():
    dps, error = run_operation('status')
    if error or not dps:
        return {'connected': False, 'error': 'EKAZA sem resposta LAN válida; confira configuração e rede.'}
    return {'connected': True, 'power': dps.get('1'), **medidas(dps)}


def check_cloud():
    try:
        cache = ROOT/'data'/'energy_history.sqlite3' if (ROOT/'data').is_dir() else ROOT/'energy_history.sqlite3'
        bridge = EnergyBridge(ler_config()['device_id'], cache_path=cache)
        now = local_now()
        result = bridge.get_energy_history(now.year, now.month, force=True)
        if not result.get('ok'):
            return {'connected': False, 'error': result.get('error', 'Cloud indisponível')}
        snapshot = bridge.snapshot()
        return {'connected': True, 'today_kwh': snapshot.get('today_kwh'),
                'current_month_kwh': snapshot.get('current_month_kwh'),
                'total_kwh': snapshot.get('total_kwh'), 'stale': snapshot.get('stale')}
    except Exception:
        return {'connected': False, 'error': 'Não foi possível consultar a Tuya Cloud.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud', action='store_true', help='Também valida consumo registrado na Tuya Cloud')
    args = parser.parse_args()
    checks = {'elgin': check_ac, 'ekaza': check_plug}
    if args.cloud:
        checks['cloud'] = check_cloud
    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        futures = {name: pool.submit(check) for name, check in checks.items()}
        results = {}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception:
                results[name] = {'connected': False, 'error': 'Falha durante a validação da conexão.'}
    print(json.dumps({'checked_at': datetime.now().isoformat(timespec='seconds'),
                      'read_only': True, **results}, ensure_ascii=False, indent=2))
    if not all(result['connected'] for result in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
