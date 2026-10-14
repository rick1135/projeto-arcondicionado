"""Comandos LAN do Elgin e entrada compatível para o painel Fluent.

run_operation deve ser chamado em worker; nunca pela thread Tk.
"""

from elgin_ac import conectar, configurar_modo, escrever_dp, ler_config, ler_status


class ElginApp:
    def __init__(self, root):
        from elgin_tray import TrayApp
        self.panel = TrayApp(root, show_at_start=True)

    @staticmethod
    def run_operation(command,value):
        try:
            cfg = ler_config()
            device, iniciais = conectar(cfg)
            try:
                def confirmar(dp, esperado):
                    dps = escrever_dp(device, dp, esperado)
                    if dps.get(str(dp)) != esperado:
                        dps = ler_status(device)
                    if dps.get(str(dp)) != esperado:
                        raise RuntimeError(f"O aparelho não confirmou o DP {dp}")
                    return dps

                if command == "status": return iniciais,None
                if command == "power": return escrever_dp(device,1,value),None
                if command == "temp": return escrever_dp(device,2,value),None
                if command == "mode": return configurar_modo(device,{"auto":"auto","cold":"cool","wet":"dry","wind":"fan"}[value]),None
                if command == "fan": return escrever_dp(device,5,value),None
                if command == "protect": return confirmar(11,value),None
                if command == "sleep": return confirmar(25,value),None
                if command == "display": return confirmar(36,value),None
                if command == "special_fan":
                    speed, restore = value
                    if speed == "strong" and iniciais.get("4") != "cold":
                        raise ValueError("Turbo está disponível apenas no modo Frio")
                    return confirmar(5,speed if speed else restore),None
                if command == "timer_off_1h":
                    if value:
                        confirmar(104,"0100")
                    return confirmar(102,value),None
                if command == "vertical": return escrever_dp(device,31,"same" if value else "off"),None
                if command == "horizontal": return escrever_dp(device,33,value),None
                if command == "swing":
                    vertical, horizontal = value
                    dps = iniciais
                    if (dps.get("31") not in (None,"off")) != vertical:
                        dps = escrever_dp(device,31,"same" if vertical else "off")
                    if (dps.get("33") is True) != horizontal:
                        dps = escrever_dp(device,33,horizontal)
                    return dps,None
                raise ValueError(f"Comando desconhecido: {command}")
            finally:
                device.close()
        except Exception as erro:
            return None,str(erro)



def main():
    from elgin_tray import main as tray_main
    tray_main()


if __name__ == "__main__":
    main()
