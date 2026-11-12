import json, os
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "file://" + os.path.join(HERE, "prototype.html")
SCREENS = [("01-login","login",1600,1000),("02-chat","chat",1600,1000),("03-recall","recall",1600,1200),
           ("04-rail","rail",900,1600),("05-dashboard","dashboard",1600,1000),("06-library","library",1600,1000),
           ("07-palette","palette",1600,900),("08-mobile","mobile",880,1716),("09-onboarding","onboarding",1600,1000),
           ("10-system","system",1600,900)]
os.makedirs(os.path.join(HERE, "screens"), exist_ok=True)
CHECK = """() => {
  const vw = innerWidth, vh = innerHeight;
  const over = [];
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    if (r.right > vw + 1.5 || r.bottom > vh + 1.5) over.push((el.className||el.tagName)+' '+JSON.stringify([Math.round(r.right),Math.round(r.bottom)]));
  });
  return {vw, vh, scroll:[document.documentElement.scrollWidth, document.documentElement.scrollHeight],
          inter: document.fonts.check('14px Inter'), mono: document.fonts.check('11px "JetBrains Mono"'),
          over: over.slice(0,6), overCount: over.length};
}"""
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox","--font-render-hinting=none"])
    report = {}
    for out, screen, w, h in SCREENS:
        pg = b.new_page(viewport={"width":w,"height":h}, device_scale_factor=2)
        pg.goto(URL + "#" + screen, wait_until="load")
        pg.wait_for_timeout(700)
        pg.evaluate("document.fonts.ready")
        m = pg.evaluate(CHECK)
        path = os.path.join(HERE, "screens", f"{out}.png")
        if screen == "mobile":
            box = pg.evaluate("()=>{const r=document.querySelector('.phone').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}")
            pg.screenshot(path=path, clip={"x":box["x"]-22,"y":box["y"]-22,"width":box["w"]+44,"height":box["h"]+44})
        else:
            pg.screenshot(path=path)
        report[out] = m
        print(f"{out:14s} {w}x{h}  fonts:{m['inter']}/{m['mono']}  scroll:{m['scroll']}  overflow:{m['overCount']}")
        if m["over"]:
            for o in m["over"]: print("     OVER", o)
        pg.close()
    b.close()
json.dump(report, open(os.path.join(HERE, "screens", "report.json"), "w"), indent=1)
