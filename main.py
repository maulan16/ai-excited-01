#!/usr/bin/env python3
"""Phoenix of fire and aurora over a mountain lake.

Procedural, standard library only. Draws a colossal fire-and-aurora
phoenix rising over a night mountain lake, then writes entry.png.

Deterministic: fixed seed, no clock, no network, no unseeded random.
Run:  MAKEFUN_OUTPUT_DIR=out python3 -P -s main.py
"""
import math
import os
import random
import struct
import zlib

W = H = 768
SEED = 20261117
rng = random.Random(SEED)

# ---------------------------------------------------------------- pixels
pix = bytearray(W * H * 3)


def _clamp(v):
    return 255 if v > 255 else (0 if v < 0 else v)


def stamp_add(cx, cy, r, cr, cg, cb, strength=1.0):
    """Additive soft disk (glow / fire / embers)."""
    x0 = int(cx - r)
    if x0 < 0:
        x0 = 0
    x1 = int(cx + r) + 1
    if x1 > W - 1:
        x1 = W - 1
    y0 = int(cy - r)
    if y0 < 0:
        y0 = 0
    y1 = int(cy + r) + 1
    if y1 > H - 1:
        y1 = H - 1
    r2 = r * r
    for y in range(y0, y1 + 1):
        dy = y - cy
        dy2 = dy * dy
        base = y * W * 3
        for x in range(x0, x1 + 1):
            dx = x - cx
            d2 = dx * dx + dy2
            if d2 < r2:
                f = 1.0 - d2 / r2
                f = f * f * strength
                i = base + x * 3
                pix[i] = _clamp(pix[i] + int(cr * f))
                pix[i + 1] = _clamp(pix[i + 1] + int(cg * f))
                pix[i + 2] = _clamp(pix[i + 2] + int(cb * f))


def stamp_over(cx, cy, r, cr, cg, cb, alpha=0.9):
    """Opaque-ish soft disk (solid body / feathers)."""
    x0 = int(cx - r)
    if x0 < 0:
        x0 = 0
    x1 = int(cx + r) + 1
    if x1 > W - 1:
        x1 = W - 1
    y0 = int(cy - r)
    if y0 < 0:
        y0 = 0
    y1 = int(cy + r) + 1
    if y1 > H - 1:
        y1 = H - 1
    r2 = r * r
    for y in range(y0, y1 + 1):
        dy = y - cy
        dy2 = dy * dy
        base = y * W * 3
        for x in range(x0, x1 + 1):
            dx = x - cx
            d2 = dx * dx + dy2
            if d2 < r2:
                f = 1.0 - d2 / r2
                f = f * f * alpha
                g = 1.0 - f
                i = base + x * 3
                pix[i] = _clamp(int(cr * f + pix[i] * g))
                pix[i + 1] = _clamp(int(cg * f + pix[i + 1] * g))
                pix[i + 2] = _clamp(int(cb * f + pix[i + 2] * g))


def lerp_col(c0, c1, t):
    return (c0[0] + (c1[0] - c0[0]) * t,
            c0[1] + (c1[1] - c0[1]) * t,
            c0[2] + (c1[2] - c0[2]) * t)


def stroke(p0, p1, p2, r0, r1, col0, col1, steps, mode="over", alpha=0.9):
    """Tapered quadratic-Bezier stroke built from overlapping disks.

    Steps are raised automatically so consecutive disks always overlap,
    even where the stroke tapers thin -- otherwise it renders dotted.
    """
    stamp = stamp_over if mode == "over" else stamp_add
    length = (math.hypot(p1[0] - p0[0], p1[1] - p0[1])
              + math.hypot(p2[0] - p1[0], p2[1] - p1[1]))
    min_r = min(r0, r1)
    need = int(length / (min_r * 0.6)) + 1 if min_r > 0 else steps
    if need > steps:
        steps = need
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        r = r0 + (r1 - r0) * t
        c = lerp_col(col0, col1, t)
        if mode == "over":
            stamp(x, y, r, c[0], c[1], c[2], alpha)
        else:
            stamp(x, y, r, c[0], c[1], c[2], alpha)


# ---------------------------------------------------------------- sky
# Per-row sky gradient (deep indigo -> violet horizon).
SKY_TOP = (7, 9, 34)
SKY_MID = (15, 20, 58)
SKY_HOR = (52, 52, 104)
sky_rows = []
for y in range(H):
    t = y / (H - 1)
    if t < 0.55:
        s = t / 0.55
        c = lerp_col(SKY_TOP, SKY_MID, s)
    else:
        s = (t - 0.55) / 0.45
        c = lerp_col(SKY_MID, SKY_HOR, s)
    sky_rows.append((int(c[0]), int(c[1]), int(c[2])))

# Aurora ribbons: two bands, centreline y(x) = base + A*sin(kx+ph).
AURORA = [
    # (base_y, amp, k, phase, sigma, color, strength)
    (120.0, 34.0, 0.011, 0.7, 26.0, (46, 235, 175), 0.85),
    (185.0, 42.0, 0.008, 2.4, 34.0, (120, 90, 255), 0.70),
    (70.0, 22.0, 0.016, 4.0, 18.0, (60, 220, 230), 0.55),
]
aurora_cx = []
for (base_y, amp, k, ph, sig, col, st) in AURORA:
    col_y = []
    for x in range(W):
        col_y.append(base_y + amp * math.sin(k * x + ph))
    aurora_cx.append((col_y, sig, col, st))

# Mountain ridges: sum-of-sines silhouettes, seeded phases.
def ridge(base, amps):
    phs = [rng.uniform(0, 6.283) for _ in amps]
    out = []
    for x in range(W):
        y = base
        for (a, k), ph in zip(amps, phs):
            y += a * math.sin(k * x + ph)
        out.append(y)
    return out


FAR = ridge(452.0, [(34.0, 0.006), (18.0, 0.017), (9.0, 0.043)])
NEAR = ridge(532.0, [(26.0, 0.009), (14.0, 0.023), (7.0, 0.061)])
LAKE_TOP = 556
FAR_COL = (30, 34, 74)
NEAR_COL = (15, 17, 42)
SNOW_COL = (205, 218, 242)
LAKE_TOP_COL = (24, 38, 76)
LAKE_BOT_COL = (7, 11, 30)

# Stars (seeded).
stars = []
for _ in range(260):
    stars.append((rng.uniform(0, W - 1), rng.uniform(0, 430),
                  rng.uniform(0.6, 1.9), rng.uniform(0.35, 1.0)))

exp = math.exp
sin = math.sin

for y in range(H):
    sr, sg, sb = sky_rows[y]
    base = y * W * 3
    in_lake = y >= LAKE_TOP
    if in_lake:
        lt = (y - LAKE_TOP) / (H - LAKE_TOP)
        lr = LAKE_TOP_COL[0] + (LAKE_BOT_COL[0] - LAKE_TOP_COL[0]) * lt
        lg = LAKE_TOP_COL[1] + (LAKE_BOT_COL[1] - LAKE_TOP_COL[1]) * lt
        lb = LAKE_TOP_COL[2] + (LAKE_BOT_COL[2] - LAKE_TOP_COL[2]) * lt
    for x in range(W):
        if in_lake:
            r, g, b = lr, lg, lb
            # warm reflection of the phoenix, shimmering with ripples
            dx = abs(x - 430) / 175.0
            if dx < 1.0:
                rip = 0.92 + 0.08 * sin(y * 0.55 + x * 0.045)
                glow = (1.0 - dx) * (1.0 - lt) * rip
                r += 235 * glow * 0.8
                g += 130 * glow * 0.8
                b += 40 * glow * 0.8
            # faint cool moon reflection, far left
            mx = abs(x - 118) / 55.0
            if mx < 1.0:
                rip = 0.8 + 0.2 * sin(y * 0.5 + x * 0.09)
                glow = (1.0 - mx) * (1.0 - lt) * rip
                r += 150 * glow * 0.5
                g += 165 * glow * 0.5
                b += 210 * glow * 0.5
            # faint horizontal ripple sheen
            if (y * 13 + x * 5) % 89 < 2:
                r += 7
                g += 9
                b += 13
        else:
            r, g, b = sr, sg, sb
            # aurora
            for col_y, sig, col, st in aurora_cx:
                d = y - col_y[x]
                dd = d * d
                if dd < 9000.0:
                    f = exp(-dd / (2.0 * sig * sig)) * st
                    # fade aurora near the horizon
                    if y > 300:
                        f *= max(0.0, 1.0 - (y - 300) / 180.0)
                    r += col[0] * f
                    g += col[1] * f
                    b += col[2] * f
            # mountains
            fy = FAR[x]
            if y >= fy:
                ny = NEAR[x]
                if y >= ny:
                    r, g, b = NEAR_COL
                else:
                    r, g, b = FAR_COL
                    # snow cap just below the far ridge line
                    if y - fy < 15:
                        s = 1.0 - (y - fy) / 15.0
                        r += (SNOW_COL[0] - r) * s * 0.8
                        g += (SNOW_COL[1] - g) * s * 0.8
                        b += (SNOW_COL[2] - b) * s * 0.8
        i = base + x * 3
        pix[i] = _clamp(int(r))
        pix[i + 1] = _clamp(int(g))
        pix[i + 2] = _clamp(int(b))

# Stars on top of the sky (before the phoenix, so the bird can occlude).
for (sx, sy, sr_, br) in stars:
    stamp_add(sx, sy, sr_ + 1.2, 200 * br, 210 * br, 255 * br, 0.8)

# Pale moon, upper left, as a cool counterpoint.
stamp_add(118, 108, 46, 120, 130, 170, 0.35)
stamp_over(118, 108, 25, 232, 238, 252, 0.95)
stamp_over(126, 102, 20, 205, 212, 235, 0.55)

# ---------------------------------------------------------------- phoenix
GOLD = (255, 196, 70)
ORANGE = (255, 122, 30)
RED = (228, 52, 44)
MAGENTA = (196, 42, 128)
VIOLET = (120, 62, 205)
CORE = (255, 244, 214)
EMBER = (255, 170, 60)

# Big soft halo first, so the bird reads as a light source.
stamp_add(430, 330, 250, 150, 70, 30, 0.28)
stamp_add(430, 330, 150, 255, 150, 50, 0.30)
stamp_add(545, 225, 90, 255, 180, 70, 0.35)

# Tail ribbons: three flowing flame ribbons down-left into the lake mist.
stroke((400, 420), (300, 520), (185, 600), 34, 8,
       ORANGE, MAGENTA, 34, "over", 0.92)
stroke((430, 430), (360, 540), (265, 648), 30, 7,
       GOLD, VIOLET, 34, "over", 0.92)
stroke((455, 425), (420, 530), (360, 640), 26, 6,
       ORANGE, RED, 30, "over", 0.92)
# Hot cores inside the ribbons.
stroke((400, 420), (300, 520), (200, 590), 13, 3,
       CORE, GOLD, 26, "add", 0.8)
stroke((430, 430), (360, 540), (275, 635), 11, 3,
       CORE, GOLD, 26, "add", 0.8)

# Body: fat bright torso from tail base up to the head, so the bird
# reads as a bird, not a streak.
stamp_over(455, 365, 72, ORANGE[0], ORANGE[1], ORANGE[2], 0.95)
stamp_over(470, 340, 58, GOLD[0], GOLD[1], GOLD[2], 0.9)
stamp_add(465, 350, 42, 255, 235, 190, 0.7)
stroke((395, 430), (460, 360), (525, 250), 58, 40,
       ORANGE, GOLD, 26, "over", 0.95)
stroke((410, 415), (465, 355), (520, 255), 30, 20,
       CORE, GOLD, 22, "add", 0.75)

# Left wing: sweeping down-left, broad and fanning.
stroke((430, 375), (280, 415), (118, 480), 78, 18,
       GOLD, RED, 30, "over", 0.95)
stroke((445, 340), (300, 360), (150, 400), 58, 14,
       ORANGE, MAGENTA, 28, "over", 0.92)
stroke((450, 310), (320, 305), (185, 335), 44, 11,
       GOLD, VIOLET, 26, "over", 0.90)
# Feather tips on the left wing.
for k in range(6):
    t = 0.45 + 0.11 * k
    u = 1.0 - t
    bx = u * u * 430 + 2 * u * t * 280 + t * t * 118
    by = u * u * 375 + 2 * u * t * 415 + t * t * 480
    stroke((bx, by), (bx - 34, by + 42), (bx - 62, by + 88),
           12, 5, RED, MAGENTA, 10, "over", 0.9)

# Right wing: thrusting up-right into the aurora (the big diagonal).
stroke((460, 320), (560, 230), (688, 118), 80, 17,
       GOLD, RED, 32, "over", 0.95)
stroke((475, 295), (575, 195), (665, 92), 60, 13,
       ORANGE, MAGENTA, 30, "over", 0.92)
stroke((480, 270), (585, 165), (640, 72), 46, 10,
       GOLD, VIOLET, 28, "over", 0.90)
# Feather tips on the right wing.
for k in range(6):
    t = 0.45 + 0.11 * k
    u = 1.0 - t
    bx = u * u * 460 + 2 * u * t * 560 + t * t * 688
    by = u * u * 320 + 2 * u * t * 230 + t * t * 118
    stroke((bx, by), (bx + 38, by - 40), (bx + 66, by - 82),
           12, 5, RED, MAGENTA, 10, "over", 0.9)

# Hot leading edges on both wings.
stroke((430, 375), (280, 415), (118, 480), 20, 6,
       CORE, GOLD, 26, "add", 0.7)
stroke((460, 320), (560, 230), (688, 118), 20, 6,
       CORE, GOLD, 28, "add", 0.7)

# Head: raised, beak pointing up-right, crest streaming back.
stamp_over(548, 222, 46, ORANGE[0], ORANGE[1], ORANGE[2], 0.95)
stamp_over(554, 216, 26, GOLD[0], GOLD[1], GOLD[2], 0.9)
stamp_add(552, 218, 18, 255, 240, 205, 0.8)
stroke((562, 202), (600, 182), (630, 170), 14, 3,
       GOLD, CORE, 12, "over", 0.95)          # beak
stroke((530, 200), (500, 168), (472, 148), 12, 4,
       RED, MAGENTA, 12, "over", 0.9)         # crest feather 1
stroke((536, 192), (512, 156), (492, 132), 10, 3,
       ORANGE, VIOLET, 12, "over", 0.9)       # crest feather 2
stamp_add(560, 212, 9, 255, 250, 230, 1.0)    # eye glow
stamp_over(560, 212, 4, 20, 8, 8, 1.0)        # eye pupil

# Embers spiralling up around the wings and tail.
for _ in range(240):
    a = rng.uniform(0, 6.283)
    rad = rng.uniform(40, 330)
    ex = 430 + rad * math.cos(a) * 1.15
    ey = 330 + rad * math.sin(a) * 0.9 - rad * 0.25
    if 0 <= ex < W and 0 <= ey < H:
        s = rng.uniform(0.5, 2.4)
        warm = rng.random()
        if warm < 0.5:
            c = (255, 190, 80)
        elif warm < 0.8:
            c = (255, 120, 40)
        else:
            c = (255, 240, 200)
        stamp_add(ex, ey, s + 1.0, c[0], c[1], c[2], 0.9)

# ---------------------------------------------------------------- vignette
for y in range(H):
    fy = 1.0 - 0.22 * ((y - H / 2) / (H / 2)) ** 2
    base = y * W * 3
    for x in range(W):
        fx = 1.0 - 0.22 * ((x - W / 2) / (W / 2)) ** 2
        f = fy * fx
        i = base + x * 3
        pix[i] = int(pix[i] * f)
        pix[i + 1] = int(pix[i + 1] * f)
        pix[i + 2] = int(pix[i + 2] * f)

# ---------------------------------------------------------------- PNG encode
def png_bytes():
    raw = bytearray()
    prev = bytearray(W * 3)
    for y in range(H):
        row = pix[y * W * 3:(y + 1) * W * 3]
        if y == 0:
            raw.append(0)
            raw += row
        else:
            raw.append(2)  # Up filter
            raw += bytes((b - p) & 0xFF for b, p in zip(row, prev))
        prev = row
    comp = zlib.compress(bytes(raw), 6)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp)
            + chunk(b"IEND", b""))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    data = png_bytes()
    with open(os.path.join(out_dir, "entry.png"), "wb") as fh:
        fh.write(data)


if __name__ == "__main__":
    main()
