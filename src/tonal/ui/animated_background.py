"""
Animated space background rendered with QPainter.

This is a QWidget subclass whose paintEvent draws an evolving
space scene: twinkling stars, drifting nebulae, floating particles,
and occasional shooting stars.

Use it as a *parent* container widget.  Child widgets that have
semi-transparent rgba backgrounds will composit over the animation.
"""
from __future__ import annotations

import math
import random

from PySide6.QtWidgets import QWidget
from PySide6.QtCore    import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui     import (
    QPainter, QColor, QPen, QBrush,
    QRadialGradient, QLinearGradient,
)


# ── tiny RNG helper ────────────────────────────────────────────────────────

def _r(lo: float, hi: float) -> float:
    return random.uniform(lo, hi)


# ── Scene primitives ───────────────────────────────────────────────────────

class _Star:
    _COLORS = [
        QColor(255, 255, 255),   # white
        QColor(200, 215, 255),   # blue-white
        QColor(255, 230, 210),   # warm white
        QColor(220, 200, 255),   # lavender
        QColor(180, 240, 255),   # ice blue
    ]

    def __init__(self, w: int, h: int) -> None:
        self.x     = _r(0, w)
        self.y     = _r(0, h)
        self.r     = _r(0.35, 2.1)
        self.base  = _r(0.35, 1.0)
        self.phase = _r(0, math.tau)
        self.speed = _r(0.012, 0.072)
        self.color = random.choice(self._COLORS)

    def step(self) -> None:
        self.phase = (self.phase + self.speed) % math.tau

    def alpha(self) -> int:
        # sin ranges -1..1, so (0.4 + 0.6*sin) ranges -0.2..1.0 → clamp to 0..255
        raw = (0.4 + 0.6 * math.sin(self.phase)) * self.base * 255
        return max(0, min(255, int(raw)))


class _Nebula:
    _PALETTES = [
        (110,  50, 220),   # violet
        ( 50,  90, 210),   # deep blue
        (200,  55, 140),   # rose
        ( 40, 155, 200),   # cyan
        (160,  40, 200),   # purple
        ( 90, 200, 140),   # emerald
    ]

    def __init__(self, w: int, h: int) -> None:
        self.w = w;  self.h = h
        self.x      = _r(0.05, 0.95) * w
        self.y      = _r(0.05, 0.95) * h
        self.radius = _r(180, 380)
        self.vx     = _r(-0.07, 0.07)
        self.vy     = _r(-0.05, 0.05)
        self.rgb    = random.choice(self._PALETTES)

    def step(self) -> None:
        pad = self.radius
        self.x = (self.x + self.vx + self.w + pad) % (self.w + 2 * pad) - pad
        self.y = (self.y + self.vy + self.h + pad) % (self.h + 2 * pad) - pad

    def draw(self, p: QPainter) -> None:
        r, g, b = self.rgb
        grad = QRadialGradient(self.x, self.y, self.radius)
        grad.setColorAt(0.00, QColor(r, g, b, 28))
        grad.setColorAt(0.45, QColor(r, g, b, 12))
        grad.setColorAt(1.00, QColor(r, g, b,  0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(
            QRectF(self.x - self.radius, self.y - self.radius,
                   self.radius * 2, self.radius * 2)
        )


class _ShootingStar:
    def __init__(self, w: int, h: int) -> None:
        self.w = w;  self.h = h
        angle    = _r(22, 58)               # degrees downward-right
        speed    = _r(12, 20)
        self.x   = _r(0, w * 0.75)
        self.y   = _r(0, h * 0.45)
        self.vx  = math.cos(math.radians(angle)) * speed
        self.vy  = math.sin(math.radians(angle)) * speed
        self.trail = _r(70, 130)             # trail px
        self.a   = 245
        self.alive = True

    def step(self) -> None:
        self.x  += self.vx
        self.y  += self.vy
        self.a  -= 8
        if self.a <= 0 or self.x > self.w + 60 or self.y > self.h + 60:
            self.alive = False

    def draw(self, p: QPainter) -> None:
        if not self.alive:
            return
        # tail end (trail length behind head)
        tx = self.x - self.vx * (self.trail / max(abs(self.vx), 0.1))
        ty = self.y - self.vy * (self.trail / max(abs(self.vy), 0.1))

        grad = QLinearGradient(self.x, self.y, tx, ty)
        a = max(0, min(255, int(self.a)))
        grad.setColorAt(0.00, QColor(255, 255, 255, a))
        grad.setColorAt(0.25, QColor(210, 220, 255, a // 2))
        grad.setColorAt(1.00, QColor(180, 190, 255,  0))
        pen = QPen(QBrush(grad), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(self.x, self.y), QPointF(tx, ty))

        # bright head dot
        p.setBrush(QBrush(QColor(255, 255, 255, a)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(self.x, self.y), 1.5, 1.5)


class _Particle:
    _COLORS = [
        QColor(150,  90, 255),   # violet
        QColor( 90, 140, 255),   # blue
        QColor(255, 130, 200),   # pink
        QColor(100, 230, 210),   # teal
        QColor(255, 200, 100),   # gold
        QColor(130, 255, 160),   # mint
    ]

    def __init__(self, w: int, h: int) -> None:
        self.w = w;  self.h = h
        self._spawn()

    def _spawn(self) -> None:
        self.x     = _r(0, self.w)
        self.y     = _r(0, self.h)
        self.r     = _r(0.7, 2.4)
        self.vx    = _r(-0.22, 0.22)
        self.vy    = _r(-0.35, -1.1)
        self.a     = _r(70, 170)
        self.fade  = _r(0.35, 1.1)
        self.color = random.choice(self._COLORS)

    def step(self) -> None:
        self.x += self.vx
        self.y += self.vy
        self.a -= self.fade
        if self.a <= 0 or self.y < -6:
            self._spawn()
            self.y = self.h + 6

    def draw(self, p: QPainter) -> None:
        c = QColor(self.color)
        c.setAlpha(max(0, min(255, int(self.a))))
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(self.x, self.y), self.r, self.r)


# ── Main animated widget ───────────────────────────────────────────────────

class AnimatedBackground(QWidget):
    """
    A QWidget that paints an animated space scene in its paintEvent.
    Child widgets with semi-transparent backgrounds will show this through.

    Usage
    -----
        content = AnimatedBackground(parent)
        content.setAutoFillBackground(False)
        splitter = QSplitter(content)          # child — add to a layout
    """

    FPS = 30

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)

        self._stars    : list[_Star]         = []
        self._nebulae  : list[_Nebula]       = []
        self._particles: list[_Particle]     = []
        self._shooters : list[_ShootingStar] = []
        self._shoot_cd : int                 = random.randint(90, 210)

        self._build_scene(1024, 700)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // self.FPS)

    # ── scene init ──────────────────────────────────────────────────────

    def _build_scene(self, w: int, h: int) -> None:
        self._stars     = [_Star(w, h)     for _ in range(170)]
        self._nebulae   = [_Nebula(w, h)   for _ in range(4)]
        self._particles = [_Particle(w, h) for _ in range(48)]
        self._shooters  = []

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._build_scene(self.width(), self.height())

    # ── animation tick ──────────────────────────────────────────────────

    def _tick(self) -> None:
        for s in self._stars:     s.step()
        for n in self._nebulae:   n.step()
        for p in self._particles: p.step()
        for ss in self._shooters: ss.step()

        self._shooters = [ss for ss in self._shooters if ss.alive]

        self._shoot_cd -= 1
        if self._shoot_cd <= 0:
            self._shooters.append(_ShootingStar(self.width(), self.height()))
            self._shoot_cd = random.randint(90, 220)

        self.update()

    # ── painting ────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── deep-space gradient background ──
        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0.00, QColor(  4,   4,  18))
        bg.setColorAt(0.40, QColor(  8,   4,  26))
        bg.setColorAt(0.75, QColor(  5,   8,  22))
        bg.setColorAt(1.00, QColor(  3,   6,  16))
        p.fillRect(self.rect(), QBrush(bg))

        # ── nebulae — additive (Screen) blending for glow ──
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        for n in self._nebulae:
            n.draw(p)

        # ── stars, particles, shooting stars — normal blending ──
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        for star in self._stars:
            a = star.alpha()
            c = QColor(star.color)
            c.setAlpha(a)
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(star.x, star.y), star.r, star.r)

            # faint glow halo on larger stars
            if star.r > 1.4 and a > 80:
                hc = QColor(star.color)
                hc.setAlpha(a // 5)
                p.setBrush(QBrush(hc))
                p.drawEllipse(QPointF(star.x, star.y), star.r * 2.8, star.r * 2.8)

        for pt in self._particles:
            pt.draw(p)

        for ss in self._shooters:
            ss.draw(p)

        p.end()
