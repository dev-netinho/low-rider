"""
MEGA CYBERTRUCK RC v1 — 6×6  |  600 × 260 × 175mm
====================================================
Baseado no v5, mas MEGA:
  - 600mm de comprimento
  - 260mm de largura (corpo) + flares
  - 175mm de altura (cabine)
  - 3 eixos / 6 rodas (6×6)
  - Rodas Arduino DC 65mm → vão 75mm passante (mesmo do v5)
  - Shell Cybertruck blindado angular
  - Compartimentos:
      2× Bateria LiPo 3S (maior autonomia)
      2× Motor DC por eixo traseiro
      Servo de direção
      2× ESC 60A
      ESP32 DevKit-V1 (slot acessível)
      Câmera 32×32mm
      Bomba d'água aquário
      Caixa de som (caçamba)

Saída: mega_cybertruck.stl + .step
"""

import cadquery as cq

# ════════════════════════════════════════════════════
#  PARÂMETROS MEGA
# ════════════════════════════════════════════════════
L   = 600.0    # comprimento total
HW  = 130.0    # meia-largura do corpo
FT  = 8.0      # espessura do piso (mais robusto)
WT  = 5.0      # espessura de parede geral

# Alturas características
H_CAB  = 175.0   # teto da cabine
H_BED  = 105.0   # borda da caçamba
H_BMP  =  48.0   # pára-choque frontal
H_HOOD =  78.0   # base do para-brisa

# Marcos X
X_WS_BOT  =  88.0    # base para-brisa
X_WS_TOP  = 138.0    # topo para-brisa / início teto
X_CAB_END = 350.0    # parede traseira cabine
X_REAR    = 600.0

# ─── 6×6: três eixos ─────────────────────────────
FRONT_AX  =  95.0    # eixo dianteiro
MID_AX    = 300.0    # eixo central
REAR_AX   = 500.0    # eixo traseiro

# Rodas DC 65mm → vão 75mm Ø passante
WHEEL_DIA  =  65.0
WR         =  37.5   # raio vão (75/2)
AZ         =  WR     # Z do centro do eixo

ARCH_HALF  =  55.0   # meia-largura horizontal do vão
ARCH_H     =  80.0   # altura do vão (>75mm para folga angular)

# Flares extra pronunciados (MEGA blindado)
FLARE_OUT  =  25.0
FLARE_T    =   WT

# ─── Baterias ────────────────────────────────────
# 2× LiPo 3S 11.1V (cada 130×44×30mm)
BAT_L, BAT_W, BAT_H = 130.0, 44.0, 30.0
BAT1_X = 165.0   # bateria 1 — zona dianteira
BAT2_X = 270.0   # bateria 2 — zona central

# ─── Motores ─────────────────────────────────────
# 2× motor DC (eixo traseiro e central)
MOT_R  = 20.0
MOT1_X = MID_AX  + 20.0
MOT2_X = REAR_AX + 20.0

# ─── Servo ───────────────────────────────────────
SERVO_L, SERVO_W = 42.0, 22.0

# ─── ESC + RX ────────────────────────────────────
ESC_L, ESC_W = 65.0, 35.0

# ─── ESP32 ───────────────────────────────────────
ESP_L, ESP_W, ESP_H = 52.0, 28.0, 14.0
ESP_X = X_WS_TOP + 15.0

# ─── Câmera ──────────────────────────────────────
CAM_S = 32.0

# ─── Bomba d'água ────────────────────────────────
PUMP_L, PUMP_W, PUMP_H = 58.0, 40.0, 40.0
PUMP_X = X_CAB_END + 15.0


# ════════════════════════════════════════════════════
#  CORPO CYBERTRUCK MEGA (loft + extrusões)
# ════════════════════════════════════════════════════

def make_body():
    hw   = HW
    hw_t = HW - 8   # afilamento no topo

    # Seção 0 — pára-choque (nariz quasi-vertical)
    s0 = [(-hw+4, 0), (hw-4, 0), (hw-4, H_BMP), (-hw+4, H_BMP)]

    # Seção 1 — capô (base para-brisa)
    s1 = [(-hw, 0), (hw, 0), (hw, H_HOOD), (-hw, H_HOOD)]

    # Seção 2 — topo para-brisa / início teto
    s2 = [(-hw,0),(hw,0),(hw,H_CAB*0.70),(hw_t,H_CAB),(-hw_t,H_CAB),(-hw,H_CAB*0.70)]

    # Seção bed
    s_bed = [(-hw, 0), (hw, 0), (hw, H_BED), (-hw, H_BED)]

    def sec(pts, prev=None, dx=0):
        wp = prev.workplane(offset=dx) if prev else cq.Workplane("YZ")
        return wp.polyline(pts).close()

    # Loft: nariz → capô
    wp = sec(s0)
    wp = sec(s1, wp, X_WS_BOT)
    front = wp.loft(combine=True)

    # Loft: capô → teto (para-brisa inclinado)
    wp = sec(s1)
    wp = sec(s2, wp, X_WS_TOP - X_WS_BOT)
    ws = wp.loft(combine=True).translate((X_WS_BOT, 0, 0))

    # Cabine uniforme
    cabin = (cq.Workplane("YZ").workplane(offset=X_WS_TOP)
             .polyline(s2).close()
             .extrude(X_CAB_END - X_WS_TOP))

    # Caçamba
    bed = (cq.Workplane("YZ").workplane(offset=X_CAB_END)
           .polyline(s_bed).close()
           .extrude(X_REAR - X_CAB_END))

    return front.union(ws).union(cabin).union(bed)


# ════════════════════════════════════════════════════
#  ESCAVAR INTERIOR
# ════════════════════════════════════════════════════

def hollow_out(body):
    cl = X_CAB_END - WT*2
    body = body.cut(
        cq.Workplane("XY").box(cl, (HW-WT)*2, H_CAB-FT-WT)
        .translate((WT+cl/2, 0, FT+(H_CAB-FT-WT)/2))
    )
    bl = X_REAR - X_CAB_END - WT*2
    body = body.cut(
        cq.Workplane("XY").box(bl, (HW-WT)*2, H_BED-FT-WT)
        .translate((X_CAB_END+WT+bl/2, 0, FT+(H_BED-FT-WT)/2))
    )
    return body


# ════════════════════════════════════════════════════
#  JANELAS
# ════════════════════════════════════════════════════

def cut_windows(body):
    depth = (HW + 18)*2
    win_zb = H_CAB * 0.60
    win_h  = H_CAB - win_zb - WT - 2

    # Para-brisa
    body = body.cut(
        cq.Workplane("XY")
        .box(X_WS_TOP-X_WS_BOT-6, (HW-WT-6)*2, H_CAB-H_HOOD-10)
        .translate(((X_WS_BOT+X_WS_TOP)/2, 0, H_HOOD+5+(H_CAB-H_HOOD-10)/2))
    )
    # Janelas dianteiras
    body = body.cut(
        cq.Workplane("XY").box(80, depth, win_h)
        .translate((X_WS_TOP+20+40, 0, win_zb+win_h/2))
    )
    # Janelas traseiras
    body = body.cut(
        cq.Workplane("XY").box(65, depth, win_h)
        .translate((X_WS_TOP+110+32, 0, win_zb+win_h/2))
    )
    # Luneta
    body = body.cut(
        cq.Workplane("XY").box(WT*3, (HW-WT-4)*2, win_h)
        .translate((X_CAB_END, 0, win_zb+win_h/2))
    )
    return body


# ════════════════════════════════════════════════════
#  VÃOS DE RODA PASSANTES — 75mm Ø × 3 EIXOS
# ════════════════════════════════════════════════════

def cut_wheel_arches(body):
    depth_pass = (HW + FLARE_OUT + 40)*2
    for ax in [FRONT_AX, MID_AX, REAR_AX]:
        body = body.cut(
            cq.Workplane("XY")
            .box(ARCH_HALF*2, depth_pass, ARCH_H)
            .translate((ax, 0, ARCH_H/2))
        )
    return body


# ════════════════════════════════════════════════════
#  FENDER FLARES MEGA (6× — um por roda)
# ════════════════════════════════════════════════════

def add_fender_flares(body):
    fw   = FLARE_OUT + FLARE_T
    fh   = ARCH_H + 6
    flen = ARCH_HALF*2 + 26

    for ax in [FRONT_AX, MID_AX, REAR_AX]:
        for sy in [+1, -1]:
            yc = sy * (HW + fw/2 - FLARE_T/2)

            outer = (cq.Workplane("XY").box(flen, fw, fh)
                     .translate((ax, yc, fh/2)))
            vao = (cq.Workplane("XY").box(flen-FLARE_T*2, fw+4, fh-FLARE_T)
                   .translate((ax, yc, FLARE_T+(fh-FLARE_T)/2)))
            flare = outer.cut(vao)
            lip = (cq.Workplane("XY").box(flen, fw, FLARE_T)
                   .translate((ax, yc, fh-FLARE_T/2)))
            body = body.union(flare).union(lip)
    return body


# ════════════════════════════════════════════════════
#  CHASSIS FRAME — mais robusto para 6×6
# ════════════════════════════════════════════════════

def add_chassis_frame(body):
    rh = 30.0; rw = 10.0; fl = 8.0
    yr = HW - 35.0

    for sy in [+1, -1]:
        yc = sy * yr
        body = body.union(
            cq.Workplane("XY").box(X_REAR, rw, rh)
            .translate((X_REAR/2, yc, FT+rh/2))
        )
        for zf in [FT, FT+rh]:
            body = body.union(
                cq.Workplane("XY").box(X_REAR, fl, 3)
                .translate((X_REAR/2, yc+sy*(rw/2+fl/2), zf))
            )

    # Travessas reforçadas — 6 eixos geram mais esforço
    cross_xs = [
        FRONT_AX-52, FRONT_AX, FRONT_AX+52,
        (FRONT_AX+MID_AX)/2,
        MID_AX-52,   MID_AX,   MID_AX+52,
        (MID_AX+REAR_AX)/2,
        REAR_AX-52,  REAR_AX,  REAR_AX+52,
        X_CAB_END+30
    ]
    for cx in cross_xs:
        body = body.union(
            cq.Workplane("XY").box(10, (yr+fl)*2, 28)
            .translate((cx, 0, FT+14))
        )
    return body


# ════════════════════════════════════════════════════
#  BATERIAS (2× LiPo 3S)
# ════════════════════════════════════════════════════

def add_batteries(body):
    for bx, label in [(BAT1_X, "BAT1"), (BAT2_X, "BAT2")]:
        outer = (cq.Workplane("XY").box(BAT_L+8, BAT_W+8, BAT_H+4)
                 .translate((bx, 0, FT+BAT_H/2+2)))
        inner = (cq.Workplane("XY").box(BAT_L, BAT_W, BAT_H+6)
                 .translate((bx, 0, FT+BAT_H/2+4)))
        tray = outer.cut(inner)
        for sy in [+1, -1]:
            tray = tray.union(
                cq.Workplane("XY").box(BAT_L+4, 6, 6)
                .translate((bx, sy*(BAT_W/2+6), FT+BAT_H+5))
            )
        body = body.union(tray)
    return body


# ════════════════════════════════════════════════════
#  MOTORES (2× DC — eixo central e traseiro)
# ════════════════════════════════════════════════════

def add_motors(body):
    for mx in [MOT1_X, MOT2_X]:
        mz = FT + 24
        plate = (cq.Workplane("XY").box(54, 54, 6).translate((mx, 0, mz)))
        hole  = (cq.Workplane("XY").circle(MOT_R).extrude(24).translate((mx, 0, mz-6)))
        plate = plate.cut(hole)
        for dx in [-22, 22]:
            for dy in [-22, 22]:
                plate = plate.cut(
                    cq.Workplane("XY").circle(1.8).extrude(10).translate((mx+dx, dy, mz-4))
                )
        brace = (cq.Workplane("XY").box(10, 54, mz-FT).translate((mx, 0, FT+(mz-FT)/2)))
        body = body.union(plate).union(brace)
    return body


# ════════════════════════════════════════════════════
#  SERVO, ESC, ESP32, CÂMERA, BOMBA
# ════════════════════════════════════════════════════

def add_servo(body):
    sx, sy2 = FRONT_AX - 55, -HW/3
    b = cq.Workplane("XY").box(SERVO_L+6, SERVO_W+4, 40).translate((sx, sy2, FT+20))
    s = cq.Workplane("XY").box(SERVO_L, SERVO_W, 42).translate((sx, sy2, FT+21))
    return body.union(b.cut(s))


def add_esc(body):
    ex = (FRONT_AX + MID_AX)/2 + 30
    tray = cq.Workplane("XY").box(ESC_L*2+20, ESC_W+10, 4).translate((ex, 0, FT+3))
    for dx in [-ESC_L/2-5, ESC_L/2+5]:
        for dy in [-ESC_W/2-2, ESC_W/2+2]:
            tray = tray.union(
                cq.Workplane("XY").circle(2.5).extrude(12).translate((ex+dx, dy, FT+3))
            )
    return body.union(tray)


def add_esp32(body):
    ez = H_CAB - ESP_H - 3
    outer = (cq.Workplane("XY").box(ESP_L+6, ESP_W+6, ESP_H+3)
             .translate((ESP_X+(ESP_L+6)/2, 0, ez+(ESP_H+3)/2)))
    slot  = (cq.Workplane("XY").box(ESP_L, ESP_W, ESP_H+5)
             .translate((ESP_X+ESP_L/2, 0, ez+(ESP_H+5)/2)))
    rack = outer.cut(slot)
    for dx in [0, ESP_L]:
        for dy in [-ESP_W/2, ESP_W/2]:
            rack = rack.union(
                cq.Workplane("XY").circle(1.6).extrude(5).translate((ESP_X+dx, dy, ez+ESP_H+3))
            )
    return body.union(rack)


def add_camera(body):
    t = 2.2
    cx = X_WS_TOP + 22
    outer = (cq.Workplane("XY").box(CAM_S+t*2, CAM_S+t*2, 7).translate((cx, 0, H_CAB+3.5)))
    inner = (cq.Workplane("XY").box(CAM_S, CAM_S, 9).translate((cx, 0, H_CAB+4.5)))
    b = outer.cut(inner)
    for dx in [-(CAM_S/2+t/2), CAM_S/2+t/2]:
        for dy in [-(CAM_S/2+t/2), CAM_S/2+t/2]:
            b = b.union(cq.Workplane("XY").circle(1.2).extrude(7).translate((cx+dx, dy, H_CAB)))
    return body.union(b)


def add_water_pump(body):
    py = -(HW - WT - PUMP_W/2 - 3)
    pz_cen = FT + PUMP_H/2 + WT
    outer = (cq.Workplane("XY").box(PUMP_L+6, PUMP_W+6, PUMP_H+4)
             .translate((PUMP_X+(PUMP_L+6)/2, py, pz_cen)))
    inner = (cq.Workplane("XY").box(PUMP_L, PUMP_W, PUMP_H+6)
             .translate((PUMP_X+PUMP_L/2, py, pz_cen+2)))
    pocket = outer.cut(inner)
    hose = cq.Workplane("YZ").center(py, pz_cen).circle(5.5).extrude(HW+30)
    pocket = pocket.cut(hose)
    return body.union(pocket)


# ════════════════════════════════════════════════════
#  BOSSES DE SUSPENSÃO (6×2 = 12 pontos)
# ════════════════════════════════════════════════════

def add_suspension(body):
    for ax in [FRONT_AX, MID_AX, REAR_AX]:
        for sy in [+1, -1]:
            yp = sy * (HW - 22)
            boss = cq.Workplane("XY").cylinder(26, 12).translate((ax, yp, FT+13))
            axle = cq.Workplane("YZ").center(yp, AZ).circle(3.0).extrude(L*2)
            boss = boss.cut(axle)
            body = body.union(boss)
    return body


# ════════════════════════════════════════════════════
#  DETALHES: ROLL BAR, PÁRA-CHOQUES, PAINÉIS
# ════════════════════════════════════════════════════

def add_details(body):
    # Roll-bar duplo
    rb_len = X_CAB_END - X_WS_TOP - 16
    body = body.union(
        cq.Workplane("XY").box(rb_len, 10, 8).translate(((X_WS_TOP+X_CAB_END)/2, 0, H_CAB))
    )
    for rx in [X_WS_TOP+22, (X_WS_TOP+X_CAB_END)/2, X_CAB_END-22]:
        body = body.union(
            cq.Workplane("XY").box(10, (HW-12)*2, 7).translate((rx, 0, H_CAB))
        )

    # Pára-choque frontal — 5 nervuras (MEGA look)
    for dy in [-80, -40, 0, 40, 80]:
        body = body.union(
            cq.Workplane("XZ").center(0, H_BMP/2).rect(9, H_BMP-4)
            .extrude(6).translate((0, dy, 0))
        )
    # Barra horizontal pára-choque
    body = body.union(
        cq.Workplane("XY").box(8, (HW-4)*2, 10).translate((4, 0, H_BMP-5))
    )

    # Pára-choque traseiro
    body = body.union(
        cq.Workplane("XY").box(10, (HW-4)*2, 18).translate((X_REAR-5, 0, FT+9))
    )

    # Plaquinhas de armadura lateral (estética blindada)
    for x_start, x_end in [(X_WS_TOP+10, X_WS_TOP+90), (X_WS_TOP+105, X_CAB_END-10)]:
        for sy in [+1, -1]:
            armor = (cq.Workplane("XY")
                     .box(x_end-x_start, 3, H_BMP+4)
                     .translate(((x_start+x_end)/2, sy*(HW+1), FT+(H_BMP+4)/2)))
            body = body.union(armor)

    return body


# ════════════════════════════════════════════════════
#  MONTAGEM MEGA
# ════════════════════════════════════════════════════

def assemble():
    print("=" * 65)
    print("  MEGA CYBERTRUCK RC  |  6×6  |  600 × 260 × 175mm")
    print("=" * 65)
    print(f"\n  3 eixos @ X={FRONT_AX:.0f}, {MID_AX:.0f}, {REAR_AX:.0f}mm")
    print(f"  Vão roda {WR*2:.0f}mm Ø passante | Rodas DC 65mm")
    print(f"  6× flares angulares blindados")

    print("\n[1/12] Corpo Cybertruck Mega (loft + extrusões)…")
    body = make_body()

    print("[2/12] Escavando interior…")
    body = hollow_out(body)

    print("[3/12] Janelas…")
    body = cut_windows(body)

    print("[4/12] Vãos de roda PASSANTES 75mm — 3 eixos (6 vãos)…")
    body = cut_wheel_arches(body)

    print("[5/12] Fender flares angulares MEGA (6×)…")
    body = add_fender_flares(body)

    print("[6/12] Chassis frame reforçado 6×6…")
    body = add_chassis_frame(body)

    print("[7/12] 2× Baterias LiPo 3S…")
    body = add_batteries(body)

    print("[8/12] 2× Motores DC…")
    body = add_motors(body)

    print("[9/12] Servo + 2×ESC…")
    body = add_servo(body)
    body = add_esc(body)

    print("[10/12] ESP32 + Câmera + Bomba d'água…")
    body = add_esp32(body)
    body = add_camera(body)
    body = add_water_pump(body)

    print("[11/12] 12× Bosses de suspensão (3 eixos × 2 lados)…")
    body = add_suspension(body)

    print("[12/12] Roll bar + pára-choques + blindagem lateral + fundo plano…")
    body = add_details(body)
    big = 1800.0
    body = body.cut(
        cq.Workplane("XY").box(big, big, big).translate((L/2, 0, -big/2-0.01))
    )

    n = len(body.val().Faces())
    print(f"\n  Faces OCC  : {n}")

    print("\nExportando mega_cybertruck.stl …")
    cq.exporters.export(body, "mega_cybertruck.stl")
    print("Exportando mega_cybertruck.step …")
    cq.exporters.export(body, "mega_cybertruck.step")
    print("\n✅ MEGA PRONTO!")
    print("=" * 65)
    return body


if __name__ == "__main__":
    assemble()
