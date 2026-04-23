# sales-agent

Trợ lý AI cho nhân viên bán hàng tại cửa hàng Tạp hóa / Nhà thuốc tại Việt Nam.

Hai luồng chính:

1. **Đơn thuốc bác sĩ kê** — nhận đơn có cấu trúc (JSON), kiểm tồn kho; item nào hết hàng hoặc không kinh doanh thì truy vấn Knowledge Graph (Neo4j) để gợi ý thuốc tương đương (cùng hoạt chất + hàm lượng + dạng bào chế, hoặc cùng nhóm ATC).
2. **Chuỗi triệu chứng (OTC)** — nhận danh sách triệu chứng + tuổi khách, vector-search các công thức OTC tương tự (pgvector) rồi gợi ý combo thuốc + liều theo độ tuổi. Có red-flag detection và chỉ gợi ý thuốc OTC.

## Stack

- Python 3.10+ + LangGraph (orchestration) + FastAPI (REST)
- Postgres + pgvector (catalog, inventory, OTC formulas với embedding)
- Neo4j (Drug / ActiveIngredient / ATCClass / EQUIVALENT_TO)
- OpenAI GPT (`gpt-4o` / `gpt-4o-mini`) + `text-embedding-3-small`

## Quick start

```bash
cp .env.example .env        # điền OPENAI_API_KEY
make install
make up                     # docker compose: postgres + neo4j
make seed                   # load seed CSV vào postgres + neo4j
make embed                  # tạo embedding cho OTC formulas
make api                    # FastAPI tại http://localhost:8000
# hoặc
make cli                    # CLI chat
```

## API

- `POST /prescriptions/check` — kiểm đơn thuốc + đề xuất thay thế.
- `POST /symptoms/advise` — tư vấn OTC theo triệu chứng.

Xem ví dụ request/response trong `examples/`.

## Disclaimer

Thông tin chỉ mang tính chất tham khảo cho nhân viên bán hàng. Không thay thế chẩn đoán và tư vấn của bác sĩ/dược sĩ có chuyên môn.
