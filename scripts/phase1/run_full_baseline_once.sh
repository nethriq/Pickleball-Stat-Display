#!/usr/bin/env bash
set -euo pipefail

# Full Phase 1 localhost baseline run (single execution).
# Assumes Django and Node are already running.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

out="$(cat /tmp/nethriq_phase1_outdir)"
user="phase1_$(date +%H%M%S)"
email="${user}@example.com"
pass='Phase1!Pass123'
video='./data/test_vids/test_video4_short.mp4'
payload='./data/stats/stats4.json'

curl -sS http://localhost:8000/api/health/ > "$out/health.json"

reg="$(curl -sS -X POST http://localhost:8000/api/register/ -H 'Content-Type: application/json' -d "{\"username\":\"$user\",\"password\":\"$pass\",\"email\":\"$email\"}")"
python - "$reg" "$out/register_response.json" <<'PY' > /tmp/nethriq_phase1_token
import json,sys,pathlib
obj=json.loads(sys.argv[1])
pathlib.Path(sys.argv[2]).write_text(json.dumps(obj,indent=2))
print(obj.get('token',''))
PY

token="$(cat /tmp/nethriq_phase1_token)"
if [[ -z "$token" ]]; then
  echo "Registration failed to return token" >&2
  exit 1
fi

upload="$(curl -sS -X POST http://localhost:8000/api/upload/ -H "Authorization: Token $token" -F "video_file=@$video" -F 'name=Phase1 Baseline Run')"
python - "$upload" "$out/upload_response.json" <<'PY' > /tmp/nethriq_phase1_jobsecret
import json,sys,pathlib
obj=json.loads(sys.argv[1])
pathlib.Path(sys.argv[2]).write_text(json.dumps(obj,indent=2))
print(obj['job_id'])
print(obj['webhook_secret'])
PY

job_id="$(sed -n '1p' /tmp/nethriq_phase1_jobsecret)"
webhook_secret="$(sed -n '2p' /tmp/nethriq_phase1_jobsecret)"

# Remove queued upload_to_pbvision task to avoid depending on external callback timing.
celery -A nethriq purge -f > "$out/celery_purge.txt" 2>&1

hook_body="$(python - "$payload" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1]))
obj.setdefault('vid','phase1-vid-001')
obj.setdefault('aiEngineVersion','phase1-engine')
if 'insights' not in obj:
    obj['insights']={'rallies':[],'player_data':[{}, {}, {}, {}], 'session':{'num_players':4}}
obj['insights'].setdefault('rallies',[])
obj['insights'].setdefault('player_data',[{}, {}, {}, {}])
obj['insights'].setdefault('session',{'num_players':4})
print(json.dumps(obj))
PY
)"

node_hook="$(curl -sS -X POST "http://localhost:3000/api/webhook/pbvision/${job_id}?token=${webhook_secret}" -H 'Content-Type: application/json' -d "$hook_body")"
echo "$node_hook" > "$out/node_webhook_response.txt"

sel="$(curl -sS -X POST "http://localhost:8000/api/jobs/${job_id}/select-player/" -H "Authorization: Token $token" -H 'Content-Type: application/json' -d '{"playerIndex":0}')"
echo "$sel" > "$out/select_player_response.json"

# Start Celery worker now that only processing task should be queued.
# Use --pidfile so we kill exactly the worker we started, not a recycled PID.
celery -A nethriq worker -l info \
  --logfile="$out/celery.log" \
  --pidfile="/tmp/nethriq_phase1_celery.pid" \
  --detach
sleep 2   # give the daemon time to write the pidfile
celery_pid="$(cat /tmp/nethriq_phase1_celery.pid 2>/dev/null || true)"
echo "$celery_pid" > /tmp/nethriq_phase1_celery_pid

python - "$token" "$job_id" "$out/job_status_timeline.txt" <<'PY' > /tmp/nethriq_phase1_final_status
import json,time,sys,urllib.request

token,job_id,out=sys.argv[1:4]
url=f'http://localhost:8000/api/jobs/{job_id}/status/'
headers={'Authorization':f'Token {token}'}
lines=[]
status='UNKNOWN'
for _ in range(60):
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=20) as r:
        data=json.loads(r.read().decode())
    status=data.get('status')
    ts=time.strftime('%Y-%m-%dT%H:%M:%S')
    lines.append(f"{ts}\t{status}")
    if status in {'COMPLETED','FAILED'}:
        break
    time.sleep(5)
open(out,'w').write('\n'.join(lines)+'\n')
print(status)
PY

final_status="$(cat /tmp/nethriq_phase1_final_status)"

if [[ -d "data/job_${job_id}/deliveries" ]]; then
  find "data/job_${job_id}/deliveries" -maxdepth 3 -type f | sort > "$out/deliverables_tree.txt"
fi

curl -sS -H "Authorization: Token $token" "http://localhost:8000/api/jobs/${job_id}/status/" > "$out/final_job_status.json"
{
  echo "job_id=$job_id"
  echo "final_status=$final_status"
  echo "user=$user"
} > "$out/baseline_summary.txt"

# Only kill Celery if we have a verified pidfile PID.
if [[ -n "$celery_pid" ]]; then
  kill "$celery_pid" 2>/dev/null || true
  rm -f /tmp/nethriq_phase1_celery.pid
fi

echo "$final_status"
