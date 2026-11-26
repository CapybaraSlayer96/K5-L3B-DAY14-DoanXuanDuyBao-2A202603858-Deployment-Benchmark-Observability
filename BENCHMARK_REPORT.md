# Benchmark & Observability Report — Day 14

**Họ tên:** Doan Xuan Duy Bao
**Ngày chạy:** 2026-11-26 (Part 7 Bước 1)
**Môi trường:** Windows 11, 8 logical CPU, Python 3.14, agent `develop/app.py` chạy trực tiếp (1 process uvicorn, không Docker). Client load test và server chạy chung một máy.

> Phần 4–5 (observability stack, benchmark scaling) chưa làm: thuộc CP8, cần Docker stack Prometheus/Grafana/Jaeger.

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

**CHƯA LÀM** (CP8): cần Docker stack, ảnh Grafana/Jaeger/Prometheus và thời gian alert firing.

## 5. Benchmark scaling (production, Locust headless)

**CHƯA LÀM** (CP8).

## 6. Kết luận

**CHƯA LÀM** (viết sau khi xong CP8).
