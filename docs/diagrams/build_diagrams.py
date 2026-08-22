"""Generate the platform's architecture diagrams as themed SVGs.

Diagrams-as-code: every figure in README.md and architecture/DESIGN.md is
emitted by this script in a light and a dark variant, sharing one visual
system (palette roles, entity-stable accents, labeled edges, 8px grid).

    python docs/diagrams/build_diagrams.py

Palette follows the validated reference instance of the dataviz method:
categorical hues are assigned to planes in fixed order and never cycled;
status colors are reserved for outcome states and always paired with a label.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

OUT = Path(__file__).parent
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str          # diagram card ground
    page: str             # page plane behind the card (transparent margin)
    ink: str              # primary text
    ink2: str             # secondary text
    muted: str            # tertiary text / edge labels
    line: str             # edges / connectors
    hairline: str         # card borders, lane rules
    accents: dict[str, str]
    status: dict[str, str]


LIGHT = Theme(
    name="light",
    surface="#fcfcfb", page="#f9f9f7",
    ink="#0b0b0b", ink2="#52514e", muted="#898781",
    line="#6f6d67", hairline="#e1e0d9",
    accents={
        "knowledge": "#2a78d6",     # slot 1 blue
        "intelligence": "#eb6834",  # slot 2 orange
        "gateway": "#1baf7a",       # slot 3 aqua
        "control": "#4a3aa7",       # slot 7 violet
        "execution": "#e87ba4",     # slot 5 magenta
        "neutral": "#898781",
    },
    status={"good": "#0ca30c", "warning": "#c98500", "serious": "#ec835a", "critical": "#d03b3b"},
)
DARK = Theme(
    name="dark",
    surface="#1a1a19", page="#0d0d0d",
    ink="#ffffff", ink2="#c3c2b7", muted="#898781",
    line="#8b8983", hairline="#2c2c2a",
    accents={
        "knowledge": "#3987e5",
        "intelligence": "#d95926",
        "gateway": "#199e70",
        "control": "#9085e9",
        "execution": "#d55181",
        "neutral": "#898781",
    },
    status={"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#e66767"},
)


def _mix(hex_a: str, hex_b: str, t: float) -> str:
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def esc(s: str) -> str:
    return html.escape(s, quote=False)


class D:
    """One SVG drawing: primitives share the theme and an element buffer."""

    def __init__(self, w: int, h: int, th: Theme, title: str) -> None:
        self.w, self.h, self.th, self.title = w, h, th, title
        self.parts: list[str] = []

    # ---- primitives -------------------------------------------------------
    def text(self, x: float, y: float, s: str, *, size: int = 13, color: str | None = None,
             anchor: str = "middle", weight: str = "normal", halo: bool = False,
             spacing: str | None = None) -> None:
        attrs = (
            f'x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{color or self.th.ink}" font-weight="{weight}"'
        )
        if spacing:
            attrs += f' letter-spacing="{spacing}"'
        if halo:
            attrs += f' paint-order="stroke" stroke="{self.th.surface}" stroke-width="5" stroke-linejoin="round"'
        self.parts.append(f"<text {attrs}>{esc(s)}</text>")

    def vtext(self, x: float, y: float, s: str, *, size: int = 11, color: str | None = None) -> None:
        self.parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" '
            f'fill="{color or self.th.ink2}" transform="rotate(-90 {x} {y})" '
            f'paint-order="stroke" stroke="{self.th.surface}" stroke-width="5" '
            f'stroke-linejoin="round">{esc(s)}</text>'
        )

    def lines(self, x: float, y: float, rows: list[str], *, size: int = 12, dy: int = 16,
              color: str | None = None, anchor: str = "middle") -> None:
        for i, row in enumerate(rows):
            self.text(x, y + i * dy, row, size=size, color=color or self.th.ink2, anchor=anchor)

    def rect(self, x: float, y: float, w: float, h: float, *, fill: str, stroke: str | None = None,
             rx: int = 10, sw: float = 1, dash: str | None = None) -> None:
        s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{sw}"'
        if dash:
            s += f' stroke-dasharray="{dash}"'
        self.parts.append(s + "/>")

    def card(self, x: float, y: float, w: float, h: float, title: str, sub: list[str] | None = None,
             *, accent: str = "neutral", title_size: int = 13, sub_size: int = 11) -> None:
        a = self.th.accents[accent]
        tint = _mix(self.th.surface, a, 0.06 if self.th.name == "light" else 0.10)
        self.rect(x, y, w, h, fill=tint, stroke=self.th.hairline, rx=9)
        self.parts.append(
            f'<path d="M {x+3} {y} h 3 v {h} h -3 a 9 9 0 0 1 0 -{h}" fill="{a}" '
            f'transform="translate(-3,0)"/>'
        )
        # simpler accent strip: rounded-left bar
        self.parts.pop()
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{a}"/>'
        )
        cx = x + w / 2
        ty = y + (h + title_size * 0.72) / 2 - (0 if not sub else (len(sub) * 14) / 2 + 1)
        self.text(cx, ty, title, size=title_size, weight="600")
        if sub:
            self.lines(cx, ty + 16, sub, size=sub_size, dy=13)

    def chip(self, x: float, y: float, label: str, accent: str) -> None:
        a = self.th.accents[accent]
        w = 9 + len(label) * 6.4
        self.rect(x, y, w, 18, fill=_mix(self.th.surface, a, 0.14), rx=9)
        self.text(x + w / 2, y + 13, label, size=10.5, color=_mix(a, self.th.ink, 0.25), weight="600", spacing="0.04em")

    def zone(self, x: float, y: float, w: float, h: float, label: str, accent: str = "neutral") -> None:
        a = self.th.accents[accent]
        self.rect(x, y, w, h, fill=_mix(self.th.surface, a, 0.035), stroke=_mix(self.th.hairline, a, 0.35),
                  rx=12, dash=None)
        self.chip(x + 12, y + 10, label, accent)

    def edge(self, pts: list[tuple[float, float]], *, label: str | None = None, color: str | None = None,
             dash: str | None = None, lx: float | None = None, ly: float | None = None,
             lsize: int = 11, marker: str = "arrow") -> None:
        c = color or self.th.line
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts)
        s = f'<path d="{d}" fill="none" stroke="{c}" stroke-width="1.6"'
        if dash:
            s += f' stroke-dasharray="{dash}"'
        if marker:
            s += f' marker-end="url(#{marker}-{self.th.name})"'
        self.parts.append(s + "/>")
        if label is not None:
            mx = lx if lx is not None else (pts[0][0] + pts[-1][0]) / 2
            my = ly if ly is not None else (pts[0][1] + pts[-1][1]) / 2 - 6
            self.text(mx, my, label, size=lsize, color=self.th.ink2, halo=True)

    def diamond(self, cx: float, cy: float, w: float, h: float, label: list[str], accent: str = "neutral") -> None:
        a = self.th.accents[accent]
        pts = f"{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}"
        self.parts.append(
            f'<polygon points="{pts}" fill="{_mix(self.th.surface, a, 0.08)}" '
            f'stroke="{_mix(self.th.hairline, a, 0.5)}" stroke-width="1.2"/>'
        )
        y0 = cy - (len(label) - 1) * 7 + 4
        for i, row in enumerate(label):
            self.text(cx, y0 + i * 14, row, size=11.5, weight="600")

    def cylinder(self, cx: float, top: float, w: float, h: float, label: list[str], accent: str) -> None:
        a = self.th.accents[accent]
        rx, ry = w / 2, 9
        fill = _mix(self.th.surface, a, 0.08 if self.th.name == "light" else 0.12)
        stroke = _mix(self.th.hairline, a, 0.5)
        self.parts.append(
            f'<path d="M {cx-rx} {top+ry} v {h-2*ry} a {rx} {ry} 0 0 0 {w} 0 v {-(h-2*ry)}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        )
        self.parts.append(
            f'<ellipse cx="{cx}" cy="{top+ry}" rx="{rx}" ry="{ry}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.2"/>'
        )
        y0 = top + h / 2 + 2 - (len(label) - 1) * 7
        for i, row in enumerate(label):
            self.text(cx, y0 + i * 14, row, size=11.5, weight="600")


    # ---- sequence-diagram helpers ----------------------------------------
    def lifeline(self, x: float, label: str, y0: float, y1: float, accent: str = "neutral") -> None:
        a = self.th.accents[accent]
        w = max(120, 30 + len(label) * 7.6)
        self.rect(x - w / 2, y0, w, 34, fill=_mix(self.th.surface, a, 0.08), stroke=self.th.hairline, rx=8)
        self.parts.append(f'<rect x="{x - w/2}" y="{y0}" width="4" height="34" rx="2" fill="{a}"/>')
        self.text(x, y0 + 22, label, size=12.5, weight="600")
        self.parts.append(
            f'<line x1="{x}" y1="{y0+34}" x2="{x}" y2="{y1}" stroke="{self.th.hairline}" '
            f'stroke-width="1.4" stroke-dasharray="3 4"/>'
        )

    def msg(self, x1: float, x2: float, y: float, label: str, *, dash: str | None = None,
            color: str | None = None, marker: str = "arrow", note: str | None = None) -> None:
        self.edge([(x1, y), (x2, y)], color=color, dash=dash, marker=marker)
        mid = (x1 + x2) / 2
        self.text(mid, y - 7, label, size=11.5, color=self.th.ink, halo=True, weight="600")
        if note:
            self.text(mid, y + 15, note, size=10.5, color=self.th.muted, halo=True)

    def selfmsg(self, x: float, y: float, label: str, note: str | None = None) -> None:
        c = self.th.line
        self.parts.append(
            f'<path d="M {x} {y} h 46 v 18 h -46" fill="none" stroke="{c}" stroke-width="1.6" '
            f'marker-end="url(#arrow-{self.th.name})"/>'
        )
        self.text(x + 56, y + 4, label, size=11.5, anchor="start", weight="600", halo=True)
        if note:
            self.text(x + 56, y + 20, note, size=10.5, color=self.th.muted, anchor="start", halo=True)

    def frame(self, x: float, y: float, w: float, h: float, label: str) -> None:
        self.rect(x, y, w, h, fill="none", stroke=self.th.muted, rx=8, dash="5 4")
        self.text(x + 10, y + 16, label, size=10.5, color=self.th.muted, anchor="start", weight="700",
                  halo=True, spacing="0.06em")

    def pill(self, cx: float, cy: float, label: str, *, accent: str | None = None,
             status: str | None = None, w: float | None = None) -> tuple[float, float]:
        col = self.th.status[status] if status else self.th.accents[accent or "neutral"]
        pw = w or max(96, 20 + len(label) * 7.4)
        fill = _mix(self.th.surface, col, 0.12 if status else 0.08)
        self.rect(cx - pw / 2, cy - 15, pw, 30, fill=fill, stroke=_mix(self.th.hairline, col, 0.5), rx=15)
        self.text(cx, cy + 4.5, label, size=12, weight="600",
                  color=_mix(col, self.th.ink, 0.55) if status else self.th.ink)
        return pw, 30

    # ---- output -----------------------------------------------------------
    def render(self) -> str:
        th = self.th
        defs = "".join(
            f'<marker id="{mid}-{th.name}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            f'markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">'
            f'<path d="M 0 1 L 9 5 L 0 9 z" fill="{col}"/></marker>'
            for mid, col in (
                ("arrow", th.line),
                ("arrow-good", th.status["good"]),
                ("arrow-bad", th.status["critical"]),
                ("arrow-warn", th.status["serious"]),
            )
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
            f'font-family="{FONT}" role="img" aria-label="{esc(self.title)}">'
            f"<defs>{defs}</defs>"
            f'<rect x="0" y="0" width="{self.w}" height="{self.h}" rx="14" fill="{th.surface}"/>'
            f'<rect x="0.5" y="0.5" width="{self.w-1}" height="{self.h-1}" rx="14" fill="none" '
            f'stroke="{th.hairline}" stroke-width="1"/>'
            + "".join(self.parts)
            + "</svg>"
        )


def emit(name: str, build) -> None:
    for th in (LIGHT, DARK):
        d = build(th)
        (OUT / f"{name}-{th.name}.svg").write_text(d.render())
    print(f"  {name}: light + dark")


# ===========================================================================
# 1. System overview
# ===========================================================================
def system_overview(th: Theme) -> D:
    d = D(980, 640, th, "System overview: five planes from sources to Azure, with telemetry feeding back")
    d.text(28, 40, "System overview", size=17, weight="700", anchor="start")
    d.text(28, 60, "AI recommends · policy authorizes · runbooks execute · verification closes the loop",
           size=12, color=th.ink2, anchor="start")

    # Sources row
    d.zone(28, 84, 924, 92, "SOURCES", "neutral")
    d.card(52, 112, 270, 48, "Git · GitHub · Azure DevOps", accent="neutral")
    d.card(354, 112, 270, 48, "Work items · ADRs · runbooks", accent="neutral")
    d.card(656, 112, 272, 48, "AKS · Azure Monitor · deploys", accent="neutral")

    # Knowledge plane
    d.zone(28, 204, 452, 118, "KNOWLEDGE PLANE — ingestion/", "knowledge")
    d.card(52, 240, 190, 62, "Governed ingestion", ["chunk · ACL · ledger / DLQ"], accent="knowledge")
    d.cylinder(330, 238, 120, 66, ["Search index", "+ metadata"], "knowledge")

    # Gateway plane
    d.zone(500, 204, 452, 118, "AI GATEWAY — app/", "gateway")
    d.card(524, 240, 404, 62, "ACL filter → retrieve → LLM → citations",
           ["authorization happens before retrieval"], accent="gateway")

    # Intelligence plane
    d.zone(28, 350, 452, 118, "INTELLIGENCE — intelligence/, product/", "intelligence")
    d.card(52, 386, 190, 62, "PR Guardian · change risk", ["deterministic, explainable"], accent="intelligence")
    d.card(266, 386, 190, 62, "Incident · deploy · drift", ["evidence-cited hypotheses"], accent="intelligence")

    # Control plane
    d.zone(500, 350, 452, 118, "CONTROL PLANE — control_plane/, state/", "control")
    d.card(524, 386, 190, 62, "Durable workflows", ["plan hashes · approvals"], accent="control")
    d.cylinder(806, 384, 130, 66, ["Audit log", "hash-chained"], "control")

    # Execution plane
    d.zone(28, 496, 700, 118, "EXECUTION — remediation/", "execution")
    d.card(52, 532, 190, 62, "Certified runbooks", ["allow-listed · reversible"], accent="execution")
    d.card(266, 532, 190, 62, "K8s / Azure adapters", ["fixed commands only"], accent="execution")
    d.card(480, 532, 224, 62, "Independent verification", ["healthy → close · else rollback"], accent="execution")

    # Azure target
    d.card(772, 532, 180, 62, "AKS / Azure", accent="neutral")

    # Edges
    d.edge([(240, 176), (240, 204)], label="events", lx=270)
    d.edge([(147, 302), (147, 350)], label="graph", lx=172)
    d.edge([(390, 304), (390, 330), (560, 330), (560, 350)], label="evidence", lx=475, ly=326)
    d.edge([(392, 271), (524, 271)], label="query", ly=264)
    d.edge([(726, 302), (726, 350)], label="grounded answers", lx=800)
    d.edge([(480, 417), (500, 417)])
    d.edge([(619, 448), (619, 496)], label="authorized plan", lx=680)
    d.edge([(704, 563), (772, 563)])
    # feedback
    d.edge([(952, 563), (964, 563), (964, 130), (928, 130)], dash="5 4")
    d.vtext(953, 400, "telemetry feeds back")
    return d


# Registry — more diagrams appended as they are built.
DIAGRAMS = {
    "system-overview": system_overview,
}


# ===========================================================================
# 2. Ingestion pipeline
# ===========================================================================
def ingestion_pipeline(th: Theme) -> D:
    d = D(980, 420, th, "Ingestion pipeline: normalize, dedupe via ledger, chunk, attach ACLs, index; failures dead-letter and replay")
    d.text(28, 40, "Knowledge plane — governed ingestion", size=16, weight="700", anchor="start")
    d.text(28, 60, "A changed file is replaced independently; failures dead-letter, never crash-loop", size=12, color=th.ink2, anchor="start")
    Y = 130
    d.card(36, Y - 26, 118, 52, "Push event", ["GitHub / ADO"], accent="neutral")
    d.card(196, Y - 26, 116, 52, "Normalize", ["events.py"], accent="knowledge")
    d.diamond(408, Y, 128, 66, ["seen before?", "ledger.py"], accent="knowledge")
    d.card(520, Y - 26, 116, 52, "Load files", ["providers.py"], accent="knowledge")
    d.card(678, Y - 26, 122, 52, "Chunk + ACL", ["AST · text · acl"], accent="knowledge")
    d.cylinder(898, Y - 34, 118, 68, ["Search", "index"], "knowledge")
    d.edge([(154, Y), (196, Y)])
    d.edge([(312, Y), (344, Y)])
    d.edge([(472, Y), (520, Y)], label="new", ly=Y - 8)
    d.edge([(636, Y), (678, Y)])
    d.edge([(800, Y), (839, Y)], label="replace", ly=Y - 8, lx=812)
    # duplicate path
    d.edge([(408, Y - 33), (408, 78), (254, 78), (254, 104)], label="duplicate — acknowledge, no work", lx=470, ly=74)
    # completion
    d.edge([(898, Y + 34), (898, 214), (466, 214)], label="ledger: completed", lx=700, ly=208)
    d.card(408, 196, 58, 36, "✓", accent="knowledge")
    d.parts.pop()  # remove card text; replace with checkmark styling
    d.text(437, 219, "done", size=11.5, weight="600")
    # failure lane
    d.zone(196, 268, 640, 116, "FAILURE PATH", "neutral")
    d.cylinder(320, 292, 110, 62, ["Dead-letter", "queue"], "intelligence")
    d.card(520, 296, 150, 54, "Operator replay", ["replay.py — explicit"], accent="intelligence")
    d.edge([(560, Y + 26), (560, 268)], label="load / index failure", color=th.status["serious"],
           marker="arrow-warn", lx=628, ly=250)
    d.edge([(375, 323), (440, 323)], marker="", color=th.hairline)
    d.edge([(377, 323), (520, 323)], label="after fix", ly=316)
    d.edge([(670, 323), (740, 323), (740, 240), (560, 156)], marker="", color=th.hairline)
    d.parts.pop()
    d.edge([(670, 323), (760, 323), (760, 176), (600, 176), (600, 156)], label="re-enqueue", lx=800, ly=250)
    return d


# ===========================================================================
# 3. Query sequence (ACL before model)
# ===========================================================================
def query_sequence(th: Theme) -> D:
    d = D(880, 580, th, "Query path: the ACL filter is compiled into the search request, so unauthorized content never reaches the model")
    d.text(28, 40, "Retrieval — authorization before the model", size=16, weight="700", anchor="start")
    d.text(28, 60, "Unauthorized content never enters the candidate set — there is nothing to redact later", size=12, color=th.ink2, anchor="start")
    C, A, S, L = 120, 360, 600, 790
    top, bot = 84, 552
    d.lifeline(C, "Caller", top, bot, "neutral")
    d.lifeline(A, "API  /v1/query", top, bot, "gateway")
    d.lifeline(S, "Azure AI Search", top, bot, "knowledge")
    d.lifeline(L, "Azure OpenAI", top, bot, "gateway")
    d.msg(C, A, 168, "question + identity groups")
    d.selfmsg(A, 196, "resolve groups · correlation ID")
    d.msg(A, S, 254, "search(query, filter = ACL)", note="trimming inside the request itself")
    d.msg(S, A, 300, "authorized chunks only", dash="4 3")
    d.frame(60, 330, 790, 62, "ALT — NO AUTHORIZED EVIDENCE")
    d.msg(A, C, 374, "explicit insufficient-evidence answer", dash="4 3")
    d.frame(60, 402, 790, 138, "ELSE — EVIDENCE FOUND")
    d.msg(A, L, 442, "question + delimited evidence", note="system prompt: evidence is data")
    d.msg(L, A, 486, "grounded answer", dash="4 3")
    d.msg(A, C, 522, "answer + citations + correlation ID", dash="4 3")
    return d


# ===========================================================================
# 4. PR Guardian sequence
# ===========================================================================
def pr_guardian_sequence(th: Theme) -> D:
    d = D(960, 560, th, "PR Guardian: webhook or CI event to deterministic risk, durable workflow and a published check")
    d.text(28, 40, "PR Guardian — event to published verdict", size=16, weight="700", anchor="start")
    d.text(28, 60, "The LLM plays no role in the decision; every input is bound into the workflow plan hash", size=12, color=th.ink2, anchor="start")
    G, I, P, W, K = 110, 330, 560, 780, 890
    top, bot = 84, 530
    d.lifeline(G, "GitHub", top, bot, "neutral")
    d.lifeline(I, "Ingress", top, bot, "gateway")
    d.lifeline(P, "PRGuardianService", top, bot, "intelligence")
    d.lifeline(W, "Control plane", top, bot, "control")
    d.msg(G, I, 170, "pull_request event", note="webhook or Actions runner")
    d.selfmsg(I, 196, "verify HMAC signature", "X-Hub-Signature-256 — fail closed")
    d.msg(I, P, 262, "normalized PR event")
    d.msg(P, G, 296, "fetch changed files")
    d.selfmsg(P, 322, "paths → services → blast radius", "deterministic risk score + evidence")
    d.msg(P, W, 392, "start_pr_review(assessment)", note="durable record · plan hash · audit event")
    d.msg(W, P, 438, "workflow_id · correlation_id", dash="4 3")
    d.msg(P, G, 478, "check run + sticky comment", note="success · neutral · action_required")
    return d


# ===========================================================================
# 5. Workflow lifecycle state machine
# ===========================================================================
def workflow_states(th: Theme) -> D:
    d = D(980, 440, th, "Workflow lifecycle: plans wait on plan-bound approval; verification decides success, rollback or escalation")
    d.text(28, 40, "Control plane — workflow lifecycle", size=16, weight="700", anchor="start")
    d.text(28, 60, "state/models.py WorkflowStatus — approval is bound to the exact plan hash", size=12, color=th.ink2, anchor="start")
    y1 = 130
    d.pill(110, y1, "RECEIVED", accent="control")
    d.pill(280, y1, "DIAGNOSING", accent="control")
    d.pill(450, y1, "PLANNED", accent="control")
    d.pill(660, y1, "EXECUTING", accent="control")
    d.pill(860, y1, "VERIFYING", accent="control")
    d.edge([(162, y1), (218, y1)])
    d.edge([(340, y1), (396, y1)])
    d.edge([(502, y1), (602, y1)], label="policy allows", ly=y1 - 22)
    d.edge([(718, y1), (804, y1)])
    y2 = 245
    d.pill(450, y2, "WAITING_APPROVAL", accent="control", w=176)
    d.edge([(450, y1 + 15), (450, y2 - 15)], label="policy requires human", lx=560, ly=(y1 + y2) / 2 + 4)
    d.edge([(538, y2), (614, y2), (632, y1 + 16)], label="plan-bound approval", lx=688, ly=y2 + 16)
    y3 = 350
    d.pill(230, y3, "ESCALATED", status="critical")
    d.pill(556, y3, "FAILED", status="critical", w=96)
    d.pill(756, y3, "ROLLED_BACK", status="serious")
    d.pill(930, y3, "SUCCEEDED", status="good")
    d.edge([(408, y2 + 13), (262, y3 - 16)], label="rejected / expired", lx=270, ly=292)
    d.edge([(676, y1 + 15), (568, y3 - 16)], label="unrecoverable", lx=584, ly=300)
    d.edge([(838, y1 + 15), (768, y3 - 16)], label="unhealthy → compensate", color=th.status["serious"],
           marker="arrow-warn", lx=796, ly=278)
    d.edge([(884, y1 + 15), (926, y3 - 16)], color=th.status["good"], marker="arrow-good")
    d.vtext(958, 218, "healthy — independent signals")
    d.edge([(756, y3 + 15), (756, 396), (230, 396), (230, y3 + 16)], label="rollback failed",
           color=th.status["critical"], marker="arrow-bad", lx=496, ly=390)
    return d


# ===========================================================================
# 6. Execution authorization flow
# ===========================================================================
def execution_flow(th: Theme) -> D:
    d = D(980, 350, th, "Execution: catalog membership, deterministic policy, plan-bound approval and simulation gate every mutation; verification decides close or rollback")
    d.text(28, 40, "Execution plane — the authorization gauntlet", size=16, weight="700", anchor="start")
    d.text(28, 60, "Agents select from a closed catalog; adapters run fixed commands — never composed strings", size=12, color=th.ink2, anchor="start")
    Y = 150
    d.card(24, Y - 26, 136, 52, "Proposed action", ["agent output"], accent="intelligence")
    d.diamond(258, Y, 132, 70, ["in certified", "catalog?"], accent="execution")
    d.diamond(448, Y, 128, 70, ["policy", "authorize()?"], accent="execution")
    d.diamond(636, Y, 132, 70, ["approval /", "simulation"], accent="execution")
    d.card(760, Y - 26, 96, 52, "Execute", ["fixed args"], accent="execution")
    d.diamond(918, Y, 100, 64, ["verify"], accent="execution")
    d.edge([(160, Y), (192, Y)])
    d.edge([(324, Y), (384, Y)], label="yes", ly=Y - 8)
    d.edge([(512, Y), (570, Y)], label="allow", ly=Y - 8)
    d.edge([(702, Y), (760, Y)], label="pass", ly=Y - 8)
    d.edge([(856, Y), (868, Y)])
    yE = 286
    d.card(300, yE - 26, 286, 52, "Escalate to human", ["audited — never silent"], accent="neutral")
    d.edge([(258, Y + 35), (258, yE), (300, yE)], label="no", lx=270, ly=Y + 62)
    d.edge([(448, Y + 35), (448, yE - 26)], label="deny", lx=468, ly=Y + 62)
    d.edge([(636, Y + 35), (560, yE - 27)], label="reject / stale", lx=680, ly=Y + 62)
    d.card(700, yE - 26, 110, 52, "Rollback", ["compensate"], accent="execution")
    d.edge([(918, Y + 32), (918, yE), (810, yE)], label="unhealthy", color=th.status["serious"], marker="arrow-warn",
           lx=940, ly=Y + 62, lsize=10.5)
    d.edge([(700, yE), (590, yE)], label="then escalate", color=th.status["critical"], marker="arrow-bad", ly=yE - 8)
    d.pill(918, 60, "close + audit", status="good", w=120)
    d.edge([(918, Y - 32), (918, 76)], label="healthy", color=th.status["good"], marker="arrow-good",
           lx=940, ly=110, lsize=10.5)
    return d


# ===========================================================================
# 7. Trust boundaries
# ===========================================================================
def trust_boundaries(th: Theme) -> D:
    d = D(880, 490, th, "Trust boundaries: each crossing has a named control; model output is proposals only")
    d.text(28, 40, "Security — trust boundaries and their crossings", size=16, weight="700", anchor="start")
    d.text(28, 60, "Every arrow is a control; nothing crosses a boundary implicitly", size=12, color=th.ink2, anchor="start")
    zx, zw = 36, 724
    d.zone(zx, 84, zw, 84, "UNTRUSTED INPUT", "neutral")
    d.card(60, 116, 184, 40, "Webhooks", accent="neutral")
    d.card(300, 116, 220, 40, "Retrieved content", accent="neutral")
    d.card(560, 116, 184, 40, "Model output", accent="neutral")
    d.zone(zx, 206, zw, 68, "GOVERNED EVIDENCE", "knowledge")
    d.card(320, 222, 220, 40, "ACL-trimmed index", accent="knowledge")
    d.zone(zx, 308, zw, 68, "DETERMINISTIC AUTHORITY", "control")
    d.card(300, 324, 270, 40, "Policy · catalog · approvals", accent="control")
    d.zone(zx, 406, zw, 54, "MUTATION SURFACE — AKS / Azure", "execution")
    d.edge([(152, 156), (152, 242), (318, 242)], label="HMAC verification — fail closed", lx=164, ly=196)
    d.edge([(410, 156), (410, 206)], label="ACL filter + injection detection", lx=410, ly=186)
    d.edge([(540, 242), (620, 242), (620, 156)], label="delimited as data", lx=634, ly=234)
    d.edge([(700, 156), (700, 176), (786, 176), (786, 344), (572, 344)])
    d.text(740, 338, "proposals only", size=11.5, color=th.ink2, halo=True, weight="600")
    d.text(688, 360, "validated against the catalog", size=10.5, color=th.muted, halo=True)
    d.edge([(435, 364), (435, 406)], label="allow-listed fixed commands", lx=435, ly=390)
    return d


# ===========================================================================
# 8. Compact README overview
# ===========================================================================
def readme_overview(th: Theme) -> D:
    d = D(980, 250, th, "The platform at a glance: sources to Azure through knowledge, gateway, agents, control and execution, with telemetry feeding back")
    Y = 108
    d.card(30, Y - 30, 128, 64, "Sources", ["Git · ADO · ops", "telemetry"], accent="neutral")
    d.card(190, Y - 30, 140, 64, "Knowledge", ["chunk · ACL", "ledger / DLQ"], accent="knowledge")
    d.card(362, Y - 30, 140, 64, "AI gateway", ["ACL → LLM", "citations"], accent="gateway")
    d.card(534, Y - 30, 140, 64, "Agents", ["PR risk · RCA", "drift · deploy"], accent="intelligence")
    d.card(706, Y - 30, 140, 64, "Control", ["workflows · policy", "approvals · audit"], accent="control")
    d.card(878, Y - 30, 74, 64, "AKS", ["Azure"], accent="execution")
    d.edge([(158, Y), (190, Y)], label="ingest", ly=Y - 40, lx=174)
    d.edge([(330, Y), (362, Y)])
    d.edge([(502, Y), (534, Y)], label="evidence", ly=Y - 40, lx=518)
    d.edge([(674, Y), (706, Y)])
    d.edge([(846, Y), (878, Y)], label="runbooks", ly=Y - 40, lx=862)
    d.edge([(915, Y + 34), (915, 200), (94, 200), (94, Y + 34)], label="verification + telemetry feed back",
           dash="5 4", lx=505, ly=194)
    d.text(490, 52, "AI recommends · policy authorizes · runbooks execute · verification closes the loop",
           size=13, weight="600")
    return d


DIAGRAMS.update({
    "ingestion-pipeline": ingestion_pipeline,
    "query-sequence": query_sequence,
    "pr-guardian-sequence": pr_guardian_sequence,
    "workflow-states": workflow_states,
    "execution-flow": execution_flow,
    "trust-boundaries": trust_boundaries,
    "readme-overview": readme_overview,
})

if __name__ == "__main__":
    print("Generating diagrams:")
    for name, build in DIAGRAMS.items():
        emit(name, build)
