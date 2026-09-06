"""Driver: run autopilot passes until every unit of work is done.

Terminates when: the E: rescue has been ingested, every completed Takeout
archive has been processed, and no downloads are still in flight.
Safe to kill and relaunch - autopilot itself is fully checkpointed.
"""
import os, re, sys, csv, time, subprocess

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
AP      = os.path.join(SCRIPTS, "autopilot.py")
STATE   = "D:/_PhotoAudit/autopilot-state.csv"
RESCUE  = "D:/_PhotoAudit/e-rescue.csv"
WATCH   = ["C:/Users/user/Downloads", "D:/", "C:/GoogleTakeout", "D:/Takeout"]
ARC_RX  = re.compile(r"^takeout[-_].*\.(tgz|tar\.gz|zip)$", re.I)
MAXRUN  = 8 * 3600
PAUSE   = 240

def done_units():
    s = set()
    if os.path.exists(STATE):
        with open(STATE, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if r:
                    s.add(r[0])
    return s

def scan():
    downloading, archives = 0, []
    for d in WATCH:
        try:
            for fn in os.listdir(d):
                if fn.lower().endswith(".crdownload"):
                    downloading += 1
                elif ARC_RX.match(fn) or (fn.lower().endswith((".tgz", ".tar.gz")) and "takeout" in fn.lower()):
                    archives.append(fn)
        except OSError:
            pass
    return downloading, archives

def rescue_complete():
    if not os.path.exists(RESCUE):
        return False
    with open(RESCUE, newline="", encoding="utf-8") as f:
        return sum(1 for r in csv.reader(f) if r) >= 2363

t0 = time.time()
n = 0
while time.time() - t0 < MAXRUN:
    n += 1
    print(f"\n########## driver pass {n}  (+{(time.time()-t0)/60:.0f} min) ##########", flush=True)
    env = dict(os.environ, AUTOPILOT_BUDGET="2700")
    subprocess.run([sys.executable, "-u", AP], env=env)

    dl, arcs = scan()
    done = done_units()
    pending = [a for a in arcs if a not in done]
    resc_ok = ("E-Drive-Rescue" in done) or not os.path.exists("D:/E-Drive-Rescue")
    print(f"  state: downloading={dl}  archives_pending={len(pending)}  rescue_ingested={resc_ok}", flush=True)

    if dl == 0 and not pending and resc_ok:
        print("\n########## ALL WORK COMPLETE ##########", flush=True)
        break
    if not rescue_complete() and dl == 0 and not pending:
        print("  waiting on E: rescue to finish...", flush=True)
    time.sleep(PAUSE)
else:
    print("\n########## driver max runtime reached - relaunch to continue ##########", flush=True)
