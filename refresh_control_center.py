#!/usr/bin/env python3
"""Refresh Hermes Control Center: gather live state, generate JSON + HTML dashboard."""
import json, os, subprocess, shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/root/hermes-control-center")
PROFILES_DIR = Path("/root/.hermes/profiles")
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def sh(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or r.stderr.strip()
    except: return ""

def read_json(p):
    try: return json.loads(Path(p).read_text())
    except: return {}

def read_file(p):
    try: return Path(p).read_text().strip()
    except: return ""

# Gather profiles
profiles_list = []
for key in sorted(PROFILES_DIR.iterdir()):
    if not key.is_dir(): continue
    profile_key = key.name
    config_path = key / "config.yaml"
    soul_path = key / "SOUL.md"
    gateway_path = key / "gateway_state.json"
    cron_file = key / "cron" / "jobs.json"

    # Profile display mapping
    display_map = {
        "personal": "Scout", "heath": "Heath", "paula": "Paula", "trader": "Trader"
    }
    role_map = {
        "personal": "Personal OS / orchestrator",
        "heath": "Family / co-pilot",
        "paula": "Family / co-pilot",
        "trader": "Trading / quant"
    }
    owns_map = {
        "personal": "General admin, Obsidian, CRM, email, schedules, household ops, AI consulting, health dashboards",
        "heath": "Heath's personal assistant tasks",
        "paula": "Paula's personal assistant tasks",
        "trader": "Market data, trading signals, portfolio tracking"
    }
    accent_map = {
        "personal": "#10b981", "heath": "#6366f1", "paula": "#ec4899", "trader": "#f59e0b"
    }

    display = display_map.get(profile_key, profile_key.capitalize())

    # Parse config
    config_raw = read_file(config_path)
    model = "unknown"
    provider = "unknown"
    base_url = ""
    fallback = []
    browser_backend = "browser-use"
    browser_cloud = "browser-use"
    terminal_backend = "local"
    reasoning = "medium"
    for line in config_raw.split("\n"):
        if line.strip().startswith("default:"):
            model = line.split(":", 1)[1].strip().strip("'\"")
        if line.strip().startswith("provider:") and not line.strip().startswith("provider_"):
            provider = line.split(":", 1)[1].strip().strip("'\"")
        if line.strip().startswith("base_url:") and not line.strip().startswith("base_url_"):
            base_url = line.split(":", 1)[1].strip().strip("'\"")

    # Soul summary
    soul_text = read_file(soul_path)
    soul_lines = [l for l in soul_text.split("\n") if l.strip() and not l.strip().startswith("|") and len(l.strip()) > 20][:8]

    # Gateway state
    gw = read_json(gateway_path)
    gateway_info = {
        "state": gw.get("gateway_state", "unknown"),
        "updated_at": gw.get("updated_at", ""),
        "active_agents": gw.get("active_agents", 0),
        "pid": gw.get("pid", 0),
        "platforms": gw.get("platforms", {})
    }

    # Cron jobs
    jobs_data = read_json(cron_file)
    jobs_list = jobs_data if isinstance(jobs_data, list) else jobs_data.get("jobs", [])
    
    # Map completed runs
    profile_jobs = []
    for job in jobs_list:
        profile_jobs.append({
            "id": job.get("job_id", ""),
            "name": job.get("name", "Unnamed"),
            "active": job.get("enabled", True),
            "state": job.get("state", "unknown"),
            "schedule": job.get("schedule", ""),
            "next_run_at": job.get("next_run_at", ""),
            "last_run_at": job.get("last_run_at", ""),
            "last_status": job.get("last_status", "never"),
            "deliver": job.get("deliver", "origin"),
            "skills": job.get("skills", []),
            "script": job.get("script", ""),
            "no_agent": job.get("no_agent", False),
            "model_snapshot": job.get("model", ""),
            "provider_snapshot": job.get("provider", ""),
        })

    config_info = {
        "model": model,
        "provider": provider,
        "base_url": base_url,
        "fallback": fallback,
        "browser_backend": browser_backend,
        "browser_cloud": browser_cloud,
        "terminal_backend": terminal_backend,
        "reasoning": reasoning,
        "config_path": str(config_path),
        "soul_path": str(soul_path),
        "cron_path": str(cron_file),
    }

    profiles_list.append({
        "display": display,
        "role": role_map.get(profile_key, ""),
        "owns": owns_map.get(profile_key, ""),
        "accent": accent_map.get(profile_key, "#6b7280"),
        "key": profile_key,
        "config": config_info,
        "soul": soul_lines,
        "gateway": gateway_info,
        "jobs": sorted(profile_jobs, key=lambda j: (0 if j["active"] else 1, j.get("next_run_at", "")))
    })

# Gather dashboard repos
dashboards = []
for repo_path, name, url_path, source_notes in [
    ("/root/health-dashboard", "Health Dashboard", "health-dashboard/docs/", "Glooko exports + WHOOP API → glucose/activity/vitals"),
    ("/root/podcast-digest", "Podcast Digest", "podcast-digest/docs/", "RSS feeds → transcript → episode summaries"),
    ("/root/personal-crm-dashboard", "Personal CRM", "personal-crm-dashboard/docs/", "LinkedIn exports → contact/relationship tracking"),
    ("/root/kids-park-dashboard", "Kids Park Dashboard", "kids-park-dashboard/", "Park visits and activity tracking"),
]:
    p = Path(repo_path)
    git_log = sh(f"git -C {repo_path} log --oneline -1 2>/dev/null")
    last_commit = git_log.split("\n")[0] if git_log else ""

    # Find index.html
    html_files = list(p.rglob("index.html"))
    public_path = str(html_files[0]) if html_files else ""
    
    dashboards.append({
        "name": name,
        "repo": repo_path,
        "public_path": public_path,
        "data_flow": source_notes,
        "last_commit": last_commit,
        "active": "EXISTS"
    })

# Build data snapshot
data = {
    "generated_at": NOW,
    "profiles": profiles_list,
    "dashboards": dashboards,
}

# Write JSON
json_path = BASE / "control-center-data.json"
json_path.write_text(json.dumps(data, indent=2, default=str))
print(f"✅ Written: {json_path}")

# Generate HTML
def render_html(d):
    # Summarize cron status counts
    total_jobs = 0
    active_jobs = 0
    paused_jobs = 0
    for p in d["profiles"]:
        for j in p["jobs"]:
            total_jobs += 1
            if j["active"]: active_jobs += 1
            else: paused_jobs += 1

    connected = sum(1 for p in d["profiles"] if p["gateway"].get("state") == "running")

    cards = ""
    for p in d["profiles"]:
        gw_state = p["gateway"].get("state", "unknown")
        gw_badge = f'<span class="badge badge-{"green" if gw_state == "running" else "gray"}">{gw_state}</span>'
        active = sum(1 for j in p["jobs"] if j["active"])
        paused = sum(1 for j in p["jobs"] if not j["active"])
        platform_info = ""
        for plat, info in p["gateway"].get("platforms", {}).items():
            s = info.get("state", "")
            platform_info += f'<span class="badge badge-{"green" if s == "connected" else "red"}">{plat}: {s}</span> '

        job_rows = ""
        for j in p["jobs"]:
            status_badge = f'<span class="badge badge-{"green" if j["last_status"] == "ok" else "red" if j["last_status"] == "error" else "gray"}">{j["last_status"] or "never"}</span>'
            state_icon = "▶" if j["active"] else "⏸"
            job_rows += f"""<tr>
                <td><span class="state-{'active' if j['active'] else 'paused'}">{state_icon}</span> {j['name']}</td>
                <td><code>{j['schedule']}</code></td>
                <td>{j['next_run_at'][:16] if j['next_run_at'] else '—'}</td>
                <td>{status_badge}</td>
                <td><code>{j['model_snapshot'] or 'script'}</code></td>
                <td>{j['deliver']}</td>
            </tr>"""

        cards += f"""<div class="profile-card">
            <div class="profile-header" style="border-left: 4px solid {p['accent']};">
                <div>
                    <h2>{p['display']} <span class="profile-key">{p['key']}</span></h2>
                    <p class="role">{p['role']}</p>
                    <p class="owns">{p['owns']}</p>
                </div>
                <div class="profile-meta">
                    {gw_badge}
                    <p><strong>Model:</strong> <code>{p['config']['model']}</code></p>
                    <p><strong>Provider:</strong> {p['config']['provider']}</p>
                    <p><strong>Agents:</strong> {p['gateway']['active_agents']}</p>
                    <div class="platform-badges">{platform_info}</div>
                </div>
            </div>
            <div class="kpi-row">
                <div class="kpi"><span class="kpi-val">{active}</span> Active Jobs</div>
                <div class="kpi"><span class="kpi-val">{paused}</span> Paused</div>
                <div class="kpi"><span class="kpi-val">{len(p['jobs'])}</span> Total</div>
                <div class="kpi"><span class="kpi-val">{p['gateway']['active_agents']}</span> Active Agents</div>
            </div>
            <table class="job-table">
                <thead><tr>
                    <th>Job</th><th>Schedule</th><th>Next Run</th><th>Last Status</th><th>Model/Script</th><th>Deliver</th>
                </tr></thead>
                <tbody>{job_rows or '<tr><td colspan="6" class="empty">No cron jobs configured</td></tr>'}</tbody>
            </table>
        </div>"""

    # Dashboard cards
    dash_cards = ""
    for db in d["dashboards"]:
        dash_cards += f"""<div class="dash-card">
            <h3>{db['name']}</h3>
            <p>{db['data_flow']}</p>
            <p class="dash-path"><code>{db['repo']}</code></p>
            <p class="dash-git">Last commit: <code>{db['last_commit'][:60]}</code></p>
            {f'<a href="file://{db["public_path"]}" class="dash-link">View Dashboard →</a>' if db['public_path'] else ''}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Control Center</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #1e293b; }}
.container {{ display: flex; min-height: 100vh; }}
.sidebar {{ width: 240px; background: #fff; border-right: 1px solid #e2e8f0; padding: 24px; position: fixed; top: 0; left: 0; height: 100vh; overflow-y: auto; }}
.sidebar h1 {{ font-size: 18px; font-weight: 600; margin-bottom: 4px; color: #0f172a; }}
.sidebar .version {{ font-size: 12px; color: #64748b; margin-bottom: 24px; }}
.sidebar .kpi-summary {{ display: flex; flex-direction: column; gap: 8px; }}
.sidebar .kpi-item {{ display: flex; justify-content: space-between; padding: 8px 12px; background: #f1f5f9; border-radius: 8px; font-size: 13px; }}
.sidebar .kpi-item .val {{ font-weight: 600; color: #0f172a; }}
.sidebar .nav-section {{ margin-top: 24px; }}
.sidebar .nav-section h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #94a3b8; margin-bottom: 8px; }}
.sidebar .nav-item {{ display: block; padding: 6px 0; font-size: 13px; color: #475569; text-decoration: none; }}
.sidebar .nav-item:hover {{ color: #10b981; }}
.main {{ margin-left: 240px; padding: 32px; flex: 1; max-width: 1200px; }}
.header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
.header h1 {{ font-size: 24px; font-weight: 600; }}
.header .stale {{ font-size: 12px; color: #64748b; }}
.profile-card {{ background: #fff; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); overflow: hidden; }}
.profile-header {{ display: flex; justify-content: space-between; padding: 20px 24px; }}
.profile-header h2 {{ font-size: 18px; font-weight: 600; }}
.profile-header .profile-key {{ font-size: 12px; font-weight: 400; color: #94a3b8; margin-left: 8px; }}
.profile-header .role {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
.profile-header .owns {{ font-size: 12px; color: #94a3b8; margin-top: 2px; }}
.profile-meta {{ text-align: right; font-size: 13px; }}
.profile-meta p {{ margin-top: 4px; }}
.profile-meta code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
.platform-badges {{ margin-top: 8px; display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 500; }}
.badge-green {{ background: #d1fae5; color: #065f46; }}
.badge-red {{ background: #fee2e2; color: #991b1b; }}
.badge-gray {{ background: #f1f5f9; color: #64748b; }}
.kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 0 24px 16px; }}
.kpi {{ background: #f8fafc; border-radius: 8px; padding: 12px; text-align: center; font-size: 13px; color: #64748b; }}
.kpi-val {{ display: block; font-size: 24px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }}
.job-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.job-table thead th {{ text-align: left; padding: 10px 16px; background: #f8fafc; border-top: 1px solid #e2e8f0; font-weight: 600; color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
.job-table tbody td {{ padding: 10px 16px; border-top: 1px solid #f1f5f9; }}
.job-table tbody tr:hover {{ background: #f8fafc; }}
.job-table code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
.state-active {{ color: #10b981; }}
.state-paused {{ color: #94a3b8; }}
.empty {{ text-align: center; color: #94a3b8; padding: 24px !important; }}
.dash-section {{ margin-top: 8px; }}
.dash-section h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; }}
.dash-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
.dash-card {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.dash-card h3 {{ font-size: 15px; font-weight: 600; margin-bottom: 8px; }}
.dash-card p {{ font-size: 13px; color: #64748b; margin-bottom: 4px; }}
.dash-card code {{ font-size: 11px; }}
.dash-link {{ display: inline-block; margin-top: 8px; font-size: 13px; color: #10b981; text-decoration: none; font-weight: 500; }}
.dash-link:hover {{ text-decoration: underline; }}
.footer {{ text-align: center; padding: 24px; font-size: 12px; color: #94a3b8; }}
</style>
</head>
<body>
<div class="container">
    <div class="sidebar">
        <h1>Hermes Control Center</h1>
        <p class="version">Generated {d['generated_at'][:16]}</p>
        <div class="kpi-summary">
            <div class="kpi-item"><span>Profiles</span><span class="val">{len(d['profiles'])}</span></div>
            <div class="kpi-item"><span>Cron Jobs</span><span class="val">{total_jobs}</span></div>
            <div class="kpi-item"><span>Active Jobs</span><span class="val">{active_jobs}</span></div>
            <div class="kpi-item"><span>Paused Jobs</span><span class="val">{paused_jobs}</span></div>
            <div class="kpi-item"><span>Connected Gateways</span><span class="val">{connected}</span></div>
            <div class="kpi-item"><span>Dashboards</span><span class="val">{len(d['dashboards'])}</span></div>
        </div>
        <div class="nav-section">
            <h3>Profiles</h3>
            {''.join(f'<a href="#{p["key"]}" class="nav-item">◈ {p["display"]}</a>' for p in d['profiles'])}
        </div>
        <div class="nav-section">
            <h3>Dashboards</h3>
            {''.join(f'<a href="#dashboards" class="nav-item">▷ {db["name"]}</a>' for db in d['dashboards'])}
        </div>
    </div>
    <div class="main">
        <div class="header">
            <h1>Operator Dashboard</h1>
            <span class="stale">Last updated: {d['generated_at'][:19]}</span>
        </div>
        {cards}
        <div class="dash-section" id="dashboards">
            <h2>Dashboards & Systems</h2>
            <div class="dash-grid">
                {dash_cards}
            </div>
        </div>
        <div class="footer">
            Hermes Agent · Scout Profile · Generated by refresh_control_center.py
        </div>
    </div>
</div>
</body>
</html>"""

    html_path = BASE / "index.html"
    html_path.write_text(html)
    print(f"✅ Written: {html_path}")

    # Write Obsidian note
    obsidian_note = f"""# Hermes Control Center

**Last generated:** {d['generated_at'][:19]}
**Location:** `file:///root/hermes-control-center/index.html`

## Overview

- **Active profiles:** {len([p for p in d['profiles'] if p['gateway']['state'] == 'running'])}/{len(d['profiles'])}
- **Total cron jobs:** {total_jobs} ({active_jobs} active, {paused_jobs} paused)
- **Dashboards:** {len(d['dashboards'])}
- **Connected gateways:** {connected}

## Profiles

"""
    for p in d['profiles']:
        active = sum(1 for j in p['jobs'] if j['active'])
        obsidian_note += f"- **{p['display']}** (`{p['key']}`): {p['role']} — {p['config']['model']} via {p['config']['provider']} — {active} active jobs\n"

    obsidian_note += f"""
## Dashboards

"""
    for db in d['dashboards']:
        obsidian_note += f"- **{db['name']}**: {db['repo']} — {db['data_flow']}\n"

    obsidian_path = BASE / "Hermes Control Center.md"
    obsidian_path.write_text(obsidian_note)
    print(f"✅ Written: {obsidian_path}")

    # Git commit
    subprocess.run("cd /root/hermes-control-center && git add -A && git commit -m 'Refresh control center data' 2>/dev/null || true", shell=True)
    subprocess.run("cd /root/hermes-control-center && git push origin main 2>/dev/null || true", shell=True)

if __name__ == "__main__":
    data = render_html(data)