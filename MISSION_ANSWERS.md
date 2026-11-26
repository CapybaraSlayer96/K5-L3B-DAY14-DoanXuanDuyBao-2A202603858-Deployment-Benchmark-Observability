# Day 14 Lab - Mission Answers

> Môi trường: Windows 11, Python 3.14 (Windows), Docker Desktop 29.9.1.
> Cổng 8000 trên máy đang bị container khác chiếm, nên các app mẫu được chạy bằng `python -m uvicorn app:app --port <cổng khác>` thay cho `python app.py`. Đặt `PYTHONUTF8=1` vì console Windows (cp1252) không in được tiếng Việt.
> Mục nào ghi **CHƯA LÀM** là chưa làm, sẽ bổ sung sau. Mọi số đo trong file lấy từ lệnh đã chạy.

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

1. API key và database URL hardcode trong code (`OPENAI_API_KEY = "sk-hardcoded-..."`, `DATABASE_URL = "postgresql://admin:password123@..."`). Push lên GitHub là lộ.
2. Không có config management: `DEBUG = True`, `MAX_TOKENS = 500` cố định trong code, không đổi được giữa dev/staging/prod.
3. Dùng `print()` thay logging có cấu trúc, và còn in ra secret (`[DEBUG] Using key: sk-hardcoded-...`). Log của lần chạy thật xác nhận key xuất hiện trong output.
4. Không có endpoint `/health`: `GET /health` trả 404, nền tảng không biết khi nào cần restart.
5. Port cố định `8000` và `host="localhost"`: không đọc biến `PORT` của Railway/Render, và `localhost` không nhận kết nối từ ngoài container.
6. `reload=True` trong code chạy chính: không dùng cho production.
7. Không xử lý graceful shutdown, không validate input (`question` nhận qua query string, không có giới hạn độ dài), không có xác thực.
8. Phụ thuộc môi trường: lần chạy đầu trên Windows trả 500 `UnicodeEncodeError` vì `print()` ghi tiếng Việt ra console cp1252. Sau khi đặt `PYTHONUTF8=1` mới chạy được.

### Exercise 1.2: Kết quả gọi bản develop

```
POST /ask  (body JSON {"question":"Hello"})   -> 422  {"detail":[{"type":"missing","loc":["query","question"],...}]}
POST /ask?question=Hello                      -> 200  {"answer":"Đây là câu trả lời từ AI agent (mock). ..."}
GET  /health                                  -> 404
```

Bản develop nhận `question` qua query, gửi JSON bị 422. Nó chạy được nhưng chưa production-ready (xem mục 1.1).

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode trong code | `config.py` đọc env var (`PORT`, `ENVIRONMENT`, `AGENT_API_KEY`...) | Đổi cấu hình giữa môi trường không cần sửa code, không lộ secret trong git |
| Secrets | `sk-...` và mật khẩu DB nằm trong source | Lấy từ env, `validate()` báo lỗi nếu thiếu `AGENT_API_KEY` ở production | Secret trong repo là lỗ hổng, phải thu hồi khi lộ |
| Health check | Không có (404) | `/health` (liveness, trả uptime/version) và `/ready` (503 khi chưa sẵn sàng) | Nền tảng biết khi nào restart và khi nào được route traffic |
| Logging | `print()`, có in cả key | `logging` với format JSON, không log secret | Log aggregator parse được, không rò rỉ thông tin nhạy cảm |
| Host/Port | `localhost:8000` cố định | `0.0.0.0` và `PORT` từ env | Chạy được trong container và trên Railway/Render |
| Shutdown | Đột ngột | `lifespan` tắt `is_ready` rồi dọn dẹp, có handler SIGTERM | Request đang chạy được hoàn thành trước khi tắt |
| Reload | `reload=True` luôn bật | Chỉ bật khi `DEBUG=true` | Reload tốn tài nguyên và không an toàn ở production |

Kết quả chạy bản production (cổng 8101): `GET /health` -> 200 kèm `status/uptime/version`, `GET /ready` -> `{"ready":true}`, `POST /ask` JSON -> 200.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. Base image: `python:3.11` (bản đầy đủ, khoảng 1 GB, chưa đo trong máy này).
2. Working directory: `/app`.
3. `COPY requirements.txt` trước để tận dụng layer cache: chỉ khi file dependencies đổi thì bước `pip install` mới chạy lại, sửa code thì không.
4. `CMD` là lệnh mặc định, `docker run <image> <lệnh khác>` ghi đè được. `ENTRYPOINT` là chương trình cố định, tham số truyền vào được nối thêm vào sau nó.

### Exercise 2.2 và 2.3: Build, image size

Build từ gốc repo: `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .` và `docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .`. Chạy container develop (map `8100:8000`, vì cổng 8000 trên máy đang bị chiếm): `POST /ask?question=What is Docker` -> 200 `{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}`.

Kích thước đo bằng `docker images` và `docker image inspect` (1667775752 B và 239811224 B):

```
- Develop:    1.67 GB (~1668 MB)   python:3.11 + COPY app
- Production: 240 MB (~240 MB)     python:3.11-slim, multi-stage
- Difference: -85.6 %  (production nhỏ hơn develop khoảng 7 lần)
```

Phân tích từ `02-docker/production/Dockerfile`:
- Stage 1 (`builder`, `python:3.11-slim`): cài `gcc`, `libpq-dev` và `pip install --user` các dependencies.
- Stage 2 (`runtime`, `python:3.11-slim`): tạo user non-root `appuser`, chỉ copy `/root/.local` từ builder cùng `main.py` và `utils/`, có `HEALTHCHECK`.
- Image nhỏ hơn vì base là `slim` (không có bộ công cụ của bản `python:3.11` đầy đủ), và compiler cùng cache apt của stage 1 không vào image cuối.

### Exercise 2.4: Docker Compose stack

Sơ đồ từ `02-docker/production/docker-compose.yml`:

```
Client -> nginx (80/443) -> agent (uvicorn, 2 worker) -> redis (session / rate limit)
                                                      -> qdrant (vector DB)
```

Cả 4 service nằm chung network `internal`. Chỉ nginx publish cổng ra ngoài; agent gọi redis và qdrant bằng tên service (`redis://redis:6379/0`, `http://qdrant:6333`). `agent` chỉ khởi động khi redis và qdrant `service_healthy`. Service agent khai báo `env_file`, nên phải có file đó (để trống vì bài dùng mock LLM).

Chạy: `docker compose -p k5-day14-docker up -d --build` trong `02-docker/production/`. Cả 4 service lên, agent/qdrant/redis `healthy`. Test qua Nginx (cổng 80):

```
GET  http://localhost/health -> HTTP/1.1 200 OK  {"status":"ok","uptime_seconds":10.0,"version":"2.0.0",...}
POST http://localhost/ask {"question":"Explain microservices"} -> HTTP/1.1 200 OK
     {"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Đã dọn bằng `docker compose -p k5-day14-docker down -v`.

## Part 3: Cloud Deployment

Nền tảng chính: Railway (trial không cần thẻ, không tự ngủ, hợp demo một ngày). Deploy thư mục `06-lab-complete/`, không deploy app mẫu.

- URL: https://k5-l3b-day14-doanxuanduybao-2a202603858-deployme-production.up.railway.app
- Kết quả 4 lệnh tự kiểm (xem `DEPLOYMENT.md`): `/health` 200, `/ready` 200, `/ask` không key 401, có key 200.
- Screenshot: **CHƯA CÓ** (`screenshots/dashboard.png`, `running.png`, `test.png`, chụp từ dashboard Railway và terminal)

### So sánh `railway.toml` với `render.yaml` (của `06-lab-complete/`)

| | `railway.toml` | `render.yaml` |
|---|---|---|
| Phạm vi | Chỉ cấu hình build và deploy của 1 service | Blueprint mô tả cả hạ tầng: web service và Key Value (Redis) |
| Build | `builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `dockerfilePath`, `dockerContext` (tính từ gốc repo) |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout` | `healthCheckPath: /health` |
| Restart | `restartPolicyType`, `restartPolicyMaxRetries` | Do Render tự quản lý |
| Biến môi trường | Không khai báo trong file, đặt bằng `railway variables set` hoặc dashboard | Khai báo trong `envVars`; secret dùng `generateValue: true` hoặc `sync: false`, giá trị nối từ service khác bằng `fromService` |
| Redis | Tạo riêng trên Railway rồi trỏ `REDIS_URL` tới nó | Khai báo luôn trong file (`type: keyvalue`), `REDIS_URL` lấy từ `connectionString` |
| Port | Railway cấp biến `PORT`, `CMD` của Dockerfile đọc `${PORT:-8000}` | Render cũng cấp `PORT`, cùng `CMD` |

Khác biệt chính: Railway tách cấu hình hạ tầng ra dashboard/CLI, Render dùng một file khai báo (infrastructure as code) nên tái tạo được cả stack bằng một lần Blueprint. Cùng một Dockerfile chạy được ở cả hai nhờ đọc `PORT` từ env.

### Exercise 3.3: Pipeline Cloud Run (`cloudbuild.yaml`, `service.yaml`), chỉ đọc, không deploy

`cloudbuild.yaml` chạy 4 bước tuần tự: (1) `test`: cài dependencies và chạy `pytest tests/`, fail thì dừng; (2) `build`: build image Docker, gắn tag theo `$COMMIT_SHA` và `latest`, dùng `--cache-from` để tận dụng layer cache; (3) `push`: đẩy mọi tag lên registry `gcr.io`; (4) `deploy`: `gcloud run deploy` ở `asia-southeast1` với min 1 và max 10 instance, 512Mi RAM, lấy `OPENAI_API_KEY` từ Secret Manager, `ENVIRONMENT=production`. `service.yaml` là định nghĩa service kiểu Knative: autoscale 1-10 instance (target 80 request đồng thời mỗi instance), `containerConcurrency: 80`, secret `AGENT_API_KEY` lấy từ Secret Manager, `livenessProbe` gọi `/health` và `startupProbe` gọi `/ready`. Image gắn theo commit SHA nên có thể rollback về đúng phiên bản.

## Part 4: API Security

### Exercise 4.1: API key (`04-api-gateway/develop`, chạy với `AGENT_API_KEY=secret-key-123`)

- Key được kiểm ở dependency `verify_api_key` (đọc header `X-API-Key`), gắn vào `/ask` bằng `Depends`.
- Thiếu key -> 401, sai key -> 403 (bản develop tách hai trường hợp).
- Rotate key: đổi biến môi trường `AGENT_API_KEY` rồi restart, không phải sửa code.

```
$ curl -i -X POST .../ask -d '{"question":"Hello"}'                          -> HTTP/1.1 401 Unauthorized
                                                                                {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
$ curl -i -X POST .../ask -H "X-API-Key: wrong" ...                          -> HTTP/1.1 403 Forbidden  {"detail":"Invalid API key."}
$ curl -i -X POST .../ask -H "X-API-Key: secret-key-123" ...                 -> HTTP/1.1 200 OK
                                                                                {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) ..."}
```

### Exercise 4.2: JWT (`04-api-gateway/production`)

Luồng: `POST /auth/token` với `student` / `demo123` -> server ký JWT (HS256, hết hạn 60 phút, chứa `sub` và `role`) -> client gửi `Authorization: Bearer <token>` -> server verify chữ ký, không cần tra DB. Tài khoản `admin`/`secret` trong `CODE_LAB.md` không tồn tại.

```
POST /auth/token {"username":"admin","password":"secret"}   -> HTTP/1.1 401 Unauthorized  {"detail":"Invalid credentials"}
POST /ask (không token)                                     -> HTTP/1.1 401 Unauthorized  {"detail":"Authentication required. Include: Authorization: Bearer <token>"}
POST /ask  Authorization: Bearer <token đã che>              -> HTTP/1.1 200 OK
   {"question":"Explain JWT","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

### Exercise 4.3: Rate limiting

- Thuật toán: sliding window counter (mỗi user một `deque` timestamp, loại bản ghi quá 60 giây).
- Giới hạn: `student` (role `user`) 10 req/phút, `teacher` (role `admin`) 100 req/phút. Bypass cho admin chính là chọn `rate_limiter_admin` theo role.
- Hạn chế: lưu trong RAM của từng process, nên nhiều worker hoặc nhiều instance sẽ mỗi nơi đếm riêng. Part 6 phải chuyển sang Redis.

Vòng lặp 15 request với token `student` (request 4.2 ở trên đã dùng 1 lượt, token che):

```
1-9  -> HTTP/1.1 200 OK   (requests_remaining giảm 8 -> 0)
10-15 -> HTTP/1.1 429 Too Many Requests
         {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":55}}
Header 429: x-ratelimit-limit: 10, x-ratelimit-remaining: 0, x-ratelimit-reset: <epoch>, retry-after: 53
```

### Exercise 4.4: Cost guard

Cách làm trong `cost_guard.py`: `check_budget(user)` chạy **trước** khi gọi LLM, và `record_usage(user, in_tokens, out_tokens)` chạy **sau**, cộng chi phí theo giá `$0.00015/1K` input và `$0.0006/1K` output. Mỗi user có `UsageRecord` theo ngày, đổi ngày thì tạo bản ghi mới (tự reset). Vượt `daily_budget_usd` (mặc định $1) trả 402. Có thêm trần toàn cục $10/ngày trả 503, và cảnh báo log khi dùng 80%.

Kiểm tra bằng `CostGuard(daily_budget_usd=0.0001)`: lần 1 qua, sau `record_usage(1000, 1000)` lần 2 trả:

```
402 {'error': 'Daily budget exceeded', 'used_usd': 0.00075, 'budget_usd': 0.0001, 'resets_at': 'midnight UTC'}
```

Hai điểm cần sửa nếu dùng thật:
- State nằm trong RAM, mất khi restart và không chia sẻ giữa instance. Production dùng Redis (`INCRBYFLOAT` + `EXPIRE`, khóa theo `user:tháng` như lời giải trong `CODE_LAB.md`).
- Trường `budget_remaining_usd` trong response `/ask` thực chất trả chi phí **đã dùng** (`usage.total_cost_usd`), không phải số còn lại. Bản `/me/usage` tính đúng `budget_remaining_usd`.

Rate limit bảo vệ tốc độ (chống spam, chống quá tải), cost guard bảo vệ tiền (chặn chi phí tích lũy dù mỗi request đều hợp lệ). Cần cả hai vì một user gửi chậm nhưng prompt rất dài vẫn đốt ngân sách.

## Part 5: Scaling & Reliability

### Exercise 5.1: Health và readiness (`05-scaling-reliability/develop`)

```
GET /health -> 200 {"status":"ok","uptime_seconds":4.8,"version":"1.0.0",...,"checks":{"memory":{"status":"ok","note":"psutil not installed"}}}
GET /ready  -> 200 {"ready":true,"in_flight_requests":1}
```

- Liveness (`/health`): process còn sống không. Fail thì nền tảng restart container.
- Readiness (`/ready`): có nhận traffic được không (đã khởi động xong, dependency như Redis kết nối được). Fail thì load balancer ngừng route vào, nhưng không restart. Vì thế khi Redis chết, `/health` vẫn 200 còn `/ready` phải 503.

### Exercise 5.2: Graceful shutdown

Trong code: `lifespan` đặt `_is_ready = False` khi tắt, rồi chờ `_in_flight_requests` về 0 (tối đa 30 giây), và `uvicorn.run(..., timeout_graceful_shutdown=30)`. `handle_sigterm` chỉ ghi log. **Chưa kiểm chứng bằng thực nghiệm**: Python Windows không gửi được SIGTERM đúng nghĩa, cần chạy trong WSL2 hoặc container. WSL2 trên máy (Ubuntu 22.04) chỉ có Python 3.10 và chưa có pip.

### Exercise 5.3: Stateless

`05-scaling-reliability/production/app.py` lưu session vào Redis nhưng **rơi về dict trong RAM nếu không kết nối được Redis**. Chứng minh vấn đề: chạy 2 process không có Redis (instance A cổng 8301, instance B cổng 8302):

```
POST A /chat {"question":"What is Docker?"}  -> 200 {"session_id":"a2f98168-...","served_by":"A","storage":"in-memory",...}
GET  A /chat/a2f98168-.../history           -> 200 (count 2)
GET  B /chat/a2f98168-.../history           -> 404 {"detail":"Session a2f98168-... not found or expired"}
```

Instance B không thấy session do A tạo, đúng như phần lý thuyết. Với Redis, mọi instance đọc chung một chỗ nên request nào đi qua instance nào cũng thấy lịch sử.

### Exercise 5.4 và 5.5: Load balancing và test stateless

Chạy trong `05-scaling-reliability/production/`: `docker compose -p k5-day14-scaling up -d --build --scale agent=3`. Có 3 agent (đều `healthy`), 1 redis, 1 nginx (cổng 8080). Gọi 10 request `POST /chat` mới, mỗi request đi vào instance khác nhau, tổng 3 / 4 / 3 theo `served_by`, `storage` đều là `redis`.

`python test_stateless.py` (5 câu trong cùng một session):

```
Request 1: [instance-ab22a5]   Request 2: [instance-5a4634]   Request 3: [instance-67dc5b]
Request 4: [instance-ab22a5]   Request 5: [instance-5a4634]
Instances used: {'instance-5a4634', 'instance-67dc5b', 'instance-ab22a5'}
Total messages: 10   (5 user + 5 assistant, đọc lại đủ)
```

Session được ghi từ 3 instance khác nhau nhưng history đọc lại đủ 10 message, vì state nằm ở Redis chứ không ở RAM từng instance. Khác với kết quả 404 ở mục 5.3 khi không có Redis.

Thử thêm failover: `docker stop k5-day14-scaling-agent-1`, rồi gửi 6 request vào cùng session: cả 6 đều 200 (Nginx chuyển sang instance còn lại). History đọc lại có `count` 20 vì code giữ tối đa 20 message gần nhất (10 message cũ cộng 12 message mới, bị cắt còn 20).

Đã dọn bằng `docker compose -p k5-day14-scaling down -v`, không còn container `k5-day14` nào.

## Part 6: Final Project

Code trong `06-lab-complete/` (đã làm hết TODO): `config.py` (đọc env), `auth.py` (`X-API-Key` -> 401, so sánh bằng `hmac.compare_digest`), `redis_client.py` (kết nối lazy, `redis_healthy()`), `rate_limiter.py` (sorted set trên Redis, 429 + `Retry-After`), `cost_guard.py` (`INCRBYFLOAT` theo ngày, 402), `main.py` (`/health`, `/ready`, `/ask`, log JSON, handler lỗi 500 không lộ stack trace), Dockerfile multi-stage, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`.

Kết quả `python check_production_ready.py` (chạy đầy đủ, có Docker, trong WSL2 Ubuntu 22.04, `os.name == posix`): **PASS 12/12, 43/43 check đạt**. Image 273 MB, build 97 giây, `docker stop` thoát với exit code 0 trong 2.3 giây, SIGTERM lúc đang có request vẫn trả 200 rồi exit code 0. Khi chạy trong WSL, Docker CLI gọi `docker-credential-desktop.exe` và báo `exec format error`, nên tôi đặt `DOCKER_CONFIG` trỏ tới thư mục tạm có `{}` cho lần chạy này (không đổi cấu hình Docker của máy).

```
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Kiểm tra thêm bằng `docker compose up` (cổng host 8400): `/health` 200, `/ready` 200, `/ask` thiếu key 401, body rỗng 422 (thông báo validation, không có stack trace), có key 200, vượt `RATE_LIMIT_PER_MINUTE=5` thì request thứ 5 trả 429 kèm `retry-after: 59`.



## AI log

| Lần | Hỏi gì | Nhận gì | Tôi tự sửa / kiểm tra thế nào |
|-----|--------|---------|-------------------------------|
| 1 | Claude Code: đọc toàn bộ tài liệu, lập danh sách task, chạy Part 1–5, viết code Part 6, chạy benchmark và observability Part 7, soạn báo cáo | Câu lệnh chạy app, code `app/`, script thí nghiệm, các câu trả lời | Mọi output (HTTP status, JSON, log, số đo) lấy từ lệnh đã chạy. Tôi tự chạy lại khi phát hiện số sai: lần chạy scale đầu có 2 agent thay vì 1 nên bỏ; thí nghiệm alert đầu bị Docker khởi động lại nên chạy lại |
| 2 | Claude Code: chẩn đoán lỗi deploy Railway từ log tôi dán (build nhầm Dockerfile Go ở gốc repo, `REDIS_URL` sai scheme làm process sập lúc import) | Hướng dẫn đặt Root Directory, sửa `redis_client.py` và `config.py` để app không sập khi URL sai | Tôi đặt Root Directory và sửa biến `REDIS_URL` trên Railway; kiểm chứng bằng 4 lệnh curl ra 200, 200, 401, 200 |
