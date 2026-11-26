# Deployment Information

## Public URL

https://k5-l3b-day14-doanxuanduybao-2a202603858-deployme-production.up.railway.app

## Platform

Railway (trial). Service build từ `06-lab-complete/` (Root Directory `/06-lab-complete`), Dockerfile multi-stage, cấu hình trong `06-lab-complete/railway.toml` (`builder = "DOCKERFILE"`, `healthcheckPath = "/health"`). Redis là một service riêng trong cùng project Railway.

## Test Commands

Đặt `BASE` là URL ở trên và `KEY` là giá trị `AGENT_API_KEY` đã đặt trên Railway (không ghi vào repo).

```bash
# Liveness: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# Readiness (Redis kết nối được): 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# /ask không có key: 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'

# /ask có key: 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $KEY" -d '{"question":"Hello"}'
```

Kết quả chạy ngày 2026-11-26 từ PowerShell: `200`, `200`, `401`, `200` theo đúng thứ tự trên.

## Environment Variables Set

Đặt trên Railway (service agent), không có giá trị nào nằm trong code hay repo:

- `AGENT_API_KEY`: khóa truy cập của agent (secret)
- `REDIS_URL`: lấy từ service Redis của Railway (secret)
- `PORT`: do Railway cấp, Dockerfile đọc qua `${PORT:-8000}`

Các biến còn lại có giá trị mặc định trong `app/config.py` nếu không đặt: `ENVIRONMENT` (`development`), `RATE_LIMIT_PER_MINUTE` (`10`), `DAILY_BUDGET_USD` (`1.0`).

## Screenshots

Cần chụp từ dashboard Railway và terminal (che `AGENT_API_KEY`, `REDIS_URL`), lưu vào `screenshots/`:

- `screenshots/dashboard.png`: trang Deployments của service agent, bản deploy Active
- `screenshots/running.png`: service đang chạy (Deploy Logs có dòng `startup` dạng JSON)
- `screenshots/test.png`: kết quả 4 lệnh curl ở trên (200, 200, 401, 200)
