# Benchmark & Observability Report — Day 14

**Họ tên:** Doan Xuan Duy Bao
**Ngày chạy:** 2026-11-26 (Part 7 Bước 1)
**Môi trường:** Windows 11, 8 logical CPU, Python 3.14, agent `develop/app.py` chạy trực tiếp (1 process uvicorn, không Docker). Client load test và server chạy chung một máy.

> Phần 4–5 chạy bằng Docker stack `k5-day14-observability` (Prometheus, Grafana, Jaeger, Locust), 2026-11-26.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM mất ~120–180 ms; 500 ms cho phép gấp ~3 lần mà người dùng vẫn thấy nhanh. Đây cũng là mặc định `--slo-p95-ms` của `load_test.py` |
| Error rate `/ask` | < 2 % | Mock cố ý trả 503 ở ~1 % request (`MOCK_ERROR_RATE`), nên 2 % chừa chỗ cho biến động mà vẫn bắt được lỗi tăng gấp đôi. Mặc định của `load_test.py` |
| Accuracy trên golden dataset | ≥ 80 % | Mặc định quality gate của `run_eval.py`. Sau khi sửa KB, v2 đạt 100 % nên có thể nâng lên 100 % để chặn regression |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

300 request mỗi mức, agent v2, lưu ở `reports/load_v2_c<N>.json`.

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.73 | 204.7 | 243.5 | 1726.5 | 0.33% | PASS |
| 10 | 43.58 | 206.8 | 238.5 | 580.1 | 1.67% | PASS |
| 50 | 80.99 | 225.4 | 943.0 | 1769.5 | 0.33% | FAIL |
| 100 | 40.22 | 698.7 | 5273.9 | 5606.6 | 1.33% | FAIL |

**Nhận xét:** RPS không tăng tuyến tính. Từ c=1 lên c=10, RPS tăng 11.7 lần (gần tuyến tính vì mỗi request chỉ chờ I/O giả lập). Từ c=10 lên c=50 chỉ tăng 1.9 lần và p95 vượt SLO (943.0 ms). Ở c=100 RPS còn 40.22 (thấp hơn c=50) và p95 lên 5273.9 ms: request xếp hàng trong cùng một process. Chưa tách được nguyên nhân chính xác (event loop một process, hay máy chạy cả client lẫn server), vì chưa đo CPU. Các lỗi 503 là mock cố ý sinh ra, không phải do tải.

### 2.2 Tail latency

300 request, concurrency 20, khởi động lại v2 với từng giá trị `MOCK_SLOW_RATE`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | Error rate |
|---|---|---|---|---|
| 0 | 219.6 | 472.9 | 511.9 | 0.00% |
| 0.03 (mặc định) | 256.5 | 500.1 | 1711.3 | 1.00% |
| 0.1 | 325.7 | 1682.8 | 1726.7 | 1.33% |

**Nhận xét:** avg tăng từ 219.6 lên 325.7 ms (khoảng 1.5 lần), còn p95 tăng từ 472.9 lên 1682.8 ms (khoảng 3.6 lần). p99 đã chạm ~1.7 s ngay từ mức 0.03 (1711.3 ms) và gần như không đổi ở mức 0.1, vì chỉ cần vài request chậm là p99 nhảy. Percentile nhạy với request chậm hơn average, nên SLO đặt theo p95/p99: average che giấu việc một nhóm nhỏ người dùng chờ rất lâu. Lưu ý ở mức 0 vẫn có p95 = 472.9 ms, cao hơn p50 gấp đôi, do hàng đợi ở concurrency 20; mỗi mức chỉ chạy một lần nên chưa đo được độ dao động giữa các lần.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.5 | 109.3 | 113.7 |
| Tổng cost (USD) | 0.000409 | 0.000764 | 0.000791 |
| Cost / câu đúng (USD) | 0.00040935 | 0.00003639 | 0.00003439 |
| Quality gate | FAIL | PASS | PASS |

Gate: v1 và v2 dùng mặc định (accuracy ≥ 80 %, không regression); v2 sau khi sửa chạy với `--min-accuracy 1.0 --baseline reports/eval_v2.json`.

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | token, hết hạn, chữ ký | Thêm một tài liệu có từ khoá kích hoạt `jwt`, nội dung so sánh API key (không hết hạn) với JWT (token có chữ ký, có hết hạn) |
| scaling-03 | cpu, memory, custom metrics | Thêm vào `KNOWLEDGE_BASE` một tài liệu có từ khoá kích hoạt `hpa`, `kubernetes`, `autoscal`, nội dung nêu CPU, memory, custom metrics |

Chỉ sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py`, không đụng `golden_dataset.jsonl`. Từ khoá mới (`hpa`, `kubernetes`, `autoscal`, `jwt`) chỉ xuất hiện trong đúng 2 câu hỏi đó nên không ảnh hưởng câu khác; eval cuối báo 0 regression.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 dùng nhiều token hơn (avg 109.3 so với 57.5 token/câu) và tốn tổng cost cao hơn (0.000764 so với 0.000409 USD), vì prompt có thêm context từ retrieval. Đổi lại accuracy tăng từ 4.3 % lên 91.3 %, nên cost / câu đúng của v2 rẻ hơn v1 khoảng 11 lần (0.00003639 so với 0.00040935 USD). Số p95 latency trong eval (1681.8 ms của v1, 1535.7 ms của v2, 233.4 ms sau khi sửa) không dùng để kết luận: chỉ 23 mẫu, một request chậm là p95 nhảy; latency phải xem ở load test.

**Chặn merge bằng exit code:** `run_eval.py` thoát với mã 1 khi quality gate fail. Chạy v1 (4.3 %) với `--baseline reports/eval_v2.json` thì báo 20 câu regression, gate FAIL, exit code 1. Bước CI:

```yaml
- name: Eval quality gate
  working-directory: 06-lab-complete/benchmark-observability/develop
  run: |
    pip install -r requirements.txt
    AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
    sleep 3
    python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85
```

Job fail khi exit code khác 0; kết hợp branch protection (bắt buộc check này pass) thì PR không merge được.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải: [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png) (3 instance, error rate 21.36 %, p95 2.23 s)
- [x] Một trace chậm trong Jaeger: [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với 2 alert cùng **firing** (`AgentHighErrorRate`, `AgentHighLatencyP95`): [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

Tải nền: Locust headless 30 user, spawn 5 user/giây; 3 instance agent. Mỗi thí nghiệm đổi cấu hình bằng `docker compose up -d --force-recreate agent` với biến môi trường tương ứng, thời gian tính từ lúc lệnh này xong tới lúc Prometheus báo trạng thái (script hỏi `/api/v1/alerts` mỗi 5 giây). Thời gian này gồm cả `for:` của rule và cửa sổ `rate()` của PromQL. Mỗi mức chỉ đo một lần.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | pending sau 25 s, firing sau 90 s | Error rate: 19.4 % (nền 0–1.6 %) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | pending sau 15 s, firing sau 148 s | Latency p95: 1.93 s (nền 0.29 s) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | pending sau 36 s, firing sau 155 s | Cost burn rate (USD/giờ): 10.2–29.7 (nền 0.5–1.0) |
| D | `docker pause` 1 instance | `AgentInstanceDown` | pending sau 15 s, firing sau 40 s | Instances up (3 xuống 2) |
| E | `AGENT_VERSION=v1` | Không có (sau 240 s alert rỗng) | Không firing | Retrieval hit ratio mất số liệu (v1 không có retrieval); tokens/s giảm từ 1619–2018 xuống 935–982 |

Thêm: cả A và B cùng áp dụng một lúc thì `AgentHighErrorRate` firing sau 91 s và `AgentHighLatencyP95` sau 127 s, và đó là lúc chụp ảnh `prometheus-alert-firing.png`. Thí nghiệm D chỉ đo thời gian alert, tôi chưa quan sát lỗi 504 ở Locust nên không kết luận về chuyện đó. Ở thí nghiệm E, p95 vẫn dưới 1 s (0.61–0.89 s) nên không chạm ngưỡng alert. Lần chạy thí nghiệm đầu tiên bị bỏ vì Docker Desktop khởi động lại giữa chừng; số liệu ở trên là của lần chạy lại.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng chỉ nhìn latency, lỗi và cost, nên v1 trả lời sai mà vẫn nhanh và không lỗi thì mọi thứ vẫn xanh. Cách phát hiện: (1) chạy eval trên golden dataset định kỳ với agent đang chạy thật, đặt quality gate như ở mục 3 (v1 chỉ đạt 4.3 %); (2) đưa chất lượng thành metric, ví dụ retrieval hit ratio của agent v2 (khoảng 0.89–0.91, và mất hẳn khi chạy v1) rồi alert khi nó tụt; (3) lấy mẫu một phần câu trả lời thật chấm bằng LLM-as-judge hoặc thu phản hồi người dùng.

### 4.3 Debug bằng trace

Trace chậm nhất tìm được:

- `trace_id`: `7a220da7d8f52f7886cfb8c04c97d7d1`
- Tổng thời gian: 1757 ms (span `POST /ask`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1640 ms, 93 %). Các span còn lại: `agent.retrieve_context` 103 ms, `agent.run` 1744 ms. Chậm do LLM (request này rơi vào nhóm "chậm bất thường" của mock), không phải code của agent.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T09:25:38.169472+00:00", "level": "INFO", "service": "observable-agent", "instance": "7b8c855b419d", "event": "llm_call", "trace_id": "7a220da7d8f52f7886cfb8c04c97d7d1", "span_id": "60039c1c3f22f5a7", "request_id": "c5fbe512ce56", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1640.1}
{"ts": "2026-11-26T09:25:38.170722+00:00", "level": "INFO", "service": "observable-agent", "instance": "7b8c855b419d", "event": "http_request", "trace_id": "7a220da7d8f52f7886cfb8c04c97d7d1", "span_id": "60039c1c3f22f5a7", "request_id": "c5fbe512ce56", "method": "POST", "route": "/ask", "status": 200, "ms": 1756.4}
```

Trace lỗi: `trace_id` `bd8991c27a55711d15219df214933ec4`, 120 ms. Span `chat mock-llm-small` (95 ms) có attribute `error.type = upstream_unavailable` và event `exception` với message "Upstream LLM error: 503 Service Unavailable (mock)". Dòng log khớp:

```json
{"ts": "2026-11-26T09:24:47.765910+00:00", "level": "INFO", "service": "observable-agent", "instance": "84c211afc779", "event": "llm_error", "trace_id": "bd8991c27a55711d15219df214933ec4", "span_id": "3a83048492bb460d", "request_id": "807d94ea71d5", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu của dòng `/ask` trong `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 40.0 | 720 | 2500 | 3600 | 60 / 4668 (1.29%) |
| 3 | 58.8 | 200 | 610 | 1700 | 86 / 6966 (1.23%) |

**Giải thích kết quả:** Scale lên 3 instance cải thiện rõ: p50 từ 720 xuống 200 ms, p95 từ 2500 xuống 610 ms, RPS từ 40.0 lên 58.8. Với 1 instance (giới hạn 0.5 CPU và 256 MB trong compose) request xếp hàng nên cả p50 cũng cao hơn 3 lần so với độ trễ một lần gọi LLM (~200 ms); 3 instance đưa p50 về đúng mức đó. RPS không tăng gấp 3 vì 100 user Locust nghỉ 0.5–2 s giữa các request, nên tổng tải bị chặn trên khoảng 100 / (1.25 s + 0.2 s) = 69 req/s; ở 3 instance chỉ còn thiếu một chút so với mức đó. p99 vẫn ~1.7 s vì mock cố ý làm chậm 3 % request (`MOCK_SLOW_RATE`), thêm instance không sửa được phần này. Nút thắt ở 1 instance là tài nguyên của chính agent; sang 3 instance thì giới hạn nằm ở bản thân LLM (đuôi chậm) và ở tốc độ phát tải của Locust. Lưu ý: lần chạy đầu của cả hai mức bị bỏ vì `docker compose run` tự dựng lại 2 replica; số trên là lần chạy lại với `--no-deps`, xác nhận bằng `docker ps` là đúng 1 và 3 container agent.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. Percentile quan trọng hơn trung bình: ở `MOCK_SLOW_RATE=0.1` avg chỉ tăng khoảng 1.5 lần nhưng p95 tăng khoảng 3.6 lần, và p99 chạm 1.7 s từ mức 0.03.
  2. Đo phải kiểm tra điều kiện thật của phép đo: nếu không xác nhận số container agent thì lần chạy "scale 1" thực ra có 2 agent và kết quả sai. Eval và load test trả lời hai câu hỏi khác nhau (đúng và nhanh), mỗi cái cần bằng chứng riêng.
  3. Alert hạ tầng không phát hiện được lỗi chất lượng (thí nghiệm E, v1 không alert nào firing), và thời gian từ lúc sự cố đến lúc alert firing luôn bằng `for:` cộng cửa sổ `rate()` (40 s tới 155 s trong các thí nghiệm trên).
- Nếu đưa agent này lên production thật, tôi sẽ thêm:
  - Alert theo retrieval hit ratio và chạy eval định kỳ trên traffic thật để bắt lỗi chất lượng.
  - Alert theo tốc độ đốt error budget (nhiều cửa sổ) thay cho ngưỡng cố định, và metric chi phí trên mỗi câu trả lời đúng.
  - Giám sát ở tầng load balancer và kiểm tra tổng hợp từ bên ngoài, vì lỗi xảy ra ở Nginx hoặc đường truyền thì metric của agent không thấy.
