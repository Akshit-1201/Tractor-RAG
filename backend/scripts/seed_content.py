"""Seed reference content through the real admin API (spec Phase 5 / M8).

Generates two PDFs (operator manual, parts & maintenance guide) and two
reference images (flashing battery warning light, engine layout diagram) and
uploads them exactly the way an admin would — through the authenticated API,
exercising validation, storage, and the full ingestion pipeline.

Usage (stack must be running):

    docker compose exec backend python -m scripts.seed_content

Idempotent: anything already present (matched by filename) is skipped.
"""

import math
import time

import fitz  # PyMuPDF
import httpx

from app.config import settings

BASE = "http://localhost:8000/api"

MANUAL_PAGES = [
    """TRACTOR OPERATOR MANUAL - SECTION 4: DASHBOARD WARNING LIGHTS

Battery / charging system light (red): A steady red battery light means the
charging system output is low. A FLASHING red battery light indicates a
charging system fault - stop the engine immediately, inspect the alternator
belt for wear or slack, and check the battery terminals for corrosion.
If the light stays on after restart, have the alternator tested.

Oil pressure light (red, oil-can symbol): Indicates engine oil pressure has
dropped below the safe threshold. Stop the engine at once and check the oil
level with the dipstick. Running the engine with this light on will cause
severe engine damage.

Coolant temperature light (red, thermometer symbol): The engine is
overheating. Idle the engine for two minutes, then shut down. Check coolant
level in the expansion tank only after the engine has cooled.

Error code E-047: Fuel injector circuit fault. The engine control unit has
detected an open circuit on one or more injectors. Check the injector wiring
harness connector under the left cowling. If the code persists, replace the
injector harness (part number IH-2210).""",
    """TRACTOR OPERATOR MANUAL - SECTION 5: SCHEDULED MAINTENANCE

Engine oil and filter: Change the engine oil and the oil filter every 250
operating hours. Use SAE 15W-40 oil meeting API CJ-4. The correct oil filter
is part number AL-120. Warm the engine before draining, and always replace
the drain plug sealing washer.

Air filter: Clean the primary air filter element every 100 hours and replace
it every 500 hours, or sooner in dusty conditions. Never wash the safety
element.

Hydraulic system: Check the hydraulic fluid level daily with the loader arms
lowered. Replace the hydraulic filter every 500 hours. Use only tractor
hydraulic fluid meeting spec THF-500.

Grease points: Grease the front axle bearings, kingpins, and three-point
hitch pivots every 50 hours using lithium EP2 grease.""",
    """TRACTOR OPERATOR MANUAL - SECTION 6: FLUID CHANGE PROCEDURES

Changing the transmission fluid: Park on level ground, lower all implements,
and let the transmission cool. Remove the drain plug at the rear of the
transmission housing and drain into a container of at least 40 litres.
Replace the transmission filter cartridge (part number TF-310). Refit the
drain plug, fill through the dipstick tube with THF-500 fluid to the FULL
mark, run the engine for five minutes, and re-check the level.

Brake adjustment: With the tractor stationary and the engine off, measure
brake pedal free travel. If free travel exceeds 40 mm, tighten the adjusting
nut on each brake rod until free travel is 20-30 mm, keeping both sides
equal to prevent pulling to one side.""",
]

GUIDE_PAGES = [
    """PARTS & MAINTENANCE GUIDE - SECTION 1: SERVICE PARTS CATALOG

AL-120   Engine oil filter. Spin-on cartridge, 3/4-16 UNF thread. Replace
         every 250 operating hours together with the engine oil.
TF-310   Transmission filter cartridge. Replace at every transmission fluid
         change (1000 hours) or when the transmission warning light shows.
AF-220   Primary air filter element. Replace every 500 hours; clean with
         compressed air (max 5 bar, from the inside out) every 100 hours.
IH-2210  Fuel injector wiring harness. Replace when error code E-047
         persists after checking the connector under the left cowling.
FB-118   Alternator fan belt. Inspect for cracks every 250 hours; correct
         deflection is 10-15 mm at the midpoint.
BT-100   Battery, 12 V 100 Ah, maintenance-free. Keep terminals clean and
         coated with terminal grease.""",
    """PARTS & MAINTENANCE GUIDE - SECTION 2: ERROR CODE REFERENCE

E-021    Coolant temperature sensor out of range. Check the sensor connector
         at the thermostat housing; replace the sensor if the code returns.
E-047    Fuel injector circuit fault. Open circuit detected on one or more
         injectors. Inspect the harness connector; replace harness IH-2210
         if the fault persists.
E-063    Hydraulic pressure below minimum. Check hydraulic fluid level and
         the suction strainer before suspecting the pump.
E-112    Alternator output low. Check fan belt FB-118 tension first; if the
         belt is within specification, have the alternator bench-tested.

A flashing warning light together with an active error code always takes
priority over scheduled work: diagnose the code before returning the
tractor to service.""",
    """PARTS & MAINTENANCE GUIDE - SECTION 3: FLUIDS AND CAPACITIES

Engine oil: SAE 15W-40, API CJ-4. Sump capacity 8.5 litres including the
filter. Drain plug torque: 45 Nm with a new sealing washer.

Transmission / hydraulic fluid: THF-500 specification only. Combined system
capacity 38 litres. Never mix fluid brands; a full flush is required when
switching suppliers.

Coolant: 50/50 ethylene glycol and distilled water. System capacity 12
litres. Replace every 2000 hours or two years.

Grease: Lithium EP2 for all pivot points. One or two strokes of the grease
gun per fitting - over-greasing damages the kingpin seals.""",
]


def make_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for page_text in pages:
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 60), page_text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def make_flashing_battery_png() -> bytes:
    """Red battery warning light with radiating flash rays on a dark dashboard."""
    doc = fitz.open()
    page = doc.new_page(width=260, height=260)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(0, 0, 260, 260))
    shape.finish(fill=(0.07, 0.11, 0.19), color=(0.07, 0.11, 0.19))
    shape.draw_circle(fitz.Point(130, 130), 62)
    shape.finish(fill=(0.85, 0.08, 0.08), color=(0.85, 0.08, 0.08))
    shape.draw_rect(fitz.Rect(98, 116, 162, 152))  # battery body
    shape.finish(color=(1, 1, 1), width=5)
    shape.draw_rect(fitz.Rect(106, 105, 120, 116))  # left terminal
    shape.finish(fill=(1, 1, 1), color=(1, 1, 1))
    shape.draw_rect(fitz.Rect(140, 105, 154, 116))  # right terminal
    shape.finish(fill=(1, 1, 1), color=(1, 1, 1))
    for angle_deg in range(0, 360, 45):  # flash rays = blinking/urgent
        angle = math.radians(angle_deg)
        inner = fitz.Point(130 + 74 * math.cos(angle), 130 + 74 * math.sin(angle))
        outer = fitz.Point(130 + 98 * math.cos(angle), 130 + 98 * math.sin(angle))
        shape.draw_line(inner, outer)
    shape.finish(color=(0.95, 0.3, 0.2), width=6)
    shape.commit()
    png = page.get_pixmap(dpi=144).tobytes("png")
    doc.close()
    return png


def make_engine_diagram_png() -> bytes:
    """Labeled engine layout diagram (top view)."""
    doc = fitz.open()
    page = doc.new_page(width=460, height=340)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(0, 0, 460, 340))
    shape.finish(fill=(1, 1, 1), color=(1, 1, 1))
    shape.draw_rect(fitz.Rect(150, 90, 320, 250))  # engine block
    shape.finish(color=(0.1, 0.15, 0.25), width=2)
    boxes = [
        (18, 70, 140, 100, "Alternator"),
        (18, 140, 140, 170, "Oil filter AL-120"),
        (18, 210, 140, 240, "Oil drain plug"),
        (330, 70, 452, 100, "Fuel injectors 1-4"),
        (330, 140, 452, 170, "Oil dipstick"),
        (330, 210, 452, 240, "Coolant tank"),
    ]
    for x0, y0, x1, y1, _ in boxes:
        shape.draw_rect(fitz.Rect(x0, y0, x1, y1))
    shape.finish(color=(0.3, 0.35, 0.45), width=1.5)
    for x0, y0, x1, y1, _ in boxes:  # connectors to the block
        y_mid = (y0 + y1) / 2
        if x1 < 150:
            shape.draw_line(fitz.Point(x1, y_mid), fitz.Point(150, y_mid))
        else:
            shape.draw_line(fitz.Point(320, y_mid), fitz.Point(x0, y_mid))
    shape.finish(color=(0.6, 0.6, 0.65), width=1)
    shape.commit()
    page.insert_text(fitz.Point(120, 40), "TRACTOR ENGINE LAYOUT - TOP VIEW", fontsize=13)
    page.insert_text(fitz.Point(196, 175), "ENGINE BLOCK", fontsize=10)
    for x0, y0, _, _, label in boxes:
        page.insert_text(fitz.Point(x0 + 6, y0 + 19), label, fontsize=9)
    png = page.get_pixmap(dpi=144).tobytes("png")
    doc.close()
    return png


def wait_indexed(client: httpx.Client, headers: dict, kind: str, item_id: int, timeout_s: int = 120) -> dict:
    item: dict = {}
    for _ in range(timeout_s):
        items = client.get(f"{BASE}/admin/{kind}", headers=headers).json()
        item = next(x for x in items if x["id"] == item_id)
        if item["status"] != "processing":
            return item
        time.sleep(1)
    return item


def main() -> None:
    client = httpx.Client(timeout=60)
    response = client.post(
        f"{BASE}/admin/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    response.raise_for_status()
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    existing = {
        "documents": {d["filename"] for d in client.get(f"{BASE}/admin/documents", headers=headers).json()},
        "images": {i["filename"] for i in client.get(f"{BASE}/admin/images", headers=headers).json()},
    }

    uploads = [
        ("documents", "demo_tractor_manual.pdf", make_pdf(MANUAL_PAGES), "application/pdf"),
        ("documents", "parts_maintenance_guide.pdf", make_pdf(GUIDE_PAGES), "application/pdf"),
        ("images", "flashing_battery_warning_light.png", make_flashing_battery_png(), "image/png"),
        ("images", "engine_layout_diagram.png", make_engine_diagram_png(), "image/png"),
    ]

    for kind, filename, data, mime in uploads:
        if filename in existing[kind]:
            print(f"skip  {filename} (already present)")
            continue
        response = client.post(
            f"{BASE}/admin/{kind}", headers=headers, files={"file": (filename, data, mime)}
        )
        response.raise_for_status()
        item = wait_indexed(client, headers, kind, response.json()["id"])
        line = f"{item['status']:9} {filename}"
        if kind == "documents":
            line += f" ({item.get('chunk_count', 0)} chunks)"
        else:
            line += f" [{item.get('category')}] {(item.get('description') or '')[:110]}"
        print(line)

    print("Seed content ready.")


if __name__ == "__main__":
    main()
