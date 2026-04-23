#!/usr/bin/env bash
# Ví dụ gọi REST API của pharmacy sales agent.
# Cách dùng:
#   chmod +x examples/curl_examples.sh
#   ./examples/curl_examples.sh            # chạy tất cả
#   ./examples/curl_examples.sh healthz    # chạy 1 case
#
# Yêu cầu: jq (để pretty-print JSON). Nếu không có, bỏ "| jq".

set -euo pipefail

API="${API:-http://localhost:8000}"
JQ="${JQ:-jq}"
if ! command -v "$JQ" >/dev/null 2>&1; then
  JQ="cat"
fi

# Docker-Postgres helpers (default to the service name in infra/docker-compose.yml).
PG_CONTAINER="${PG_CONTAINER:-sales_agent_pg}"
PG_USER="${PG_USER:-sales}"
PG_DB="${PG_DB:-sales_agent}"

psql_exec() {
  # Usage: psql_exec "SQL string"
  docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -c "$1"
}

hr() { printf '\n--- %s ---\n' "$1"; }

healthz() {
  hr "GET $API/healthz"
  curl -fsS "$API/healthz" | $JQ
}

readyz() {
  hr "GET $API/readyz"
  curl -fsS "$API/readyz" | $JQ
}

# Kịch bản 1 — đơn thuốc 3 item, 2 item hết hàng theo seed mặc định:
#   SKU-001 Panadol 500mg (qty=0)  + SKU-014 Bromhexin 8mg (qty=0).
# Kỳ vọng: Panadol out_of_stock -> substitutes paracetamol (Hapacol 500, Panadol Extra...),
#          Amoxicillin in_stock (rx_only),
#          Bromhexin out_of_stock -> substitutes Ambroxol 30mg.
rx_mixed() {
  hr "POST $API/prescriptions/check — đơn 3 item (2 hết hàng: Panadol + Bromhexin)"
  curl -fsS -X POST "$API/prescriptions/check" \
    -H 'content-type: application/json' \
    -d '{
      "patient": {"age_years": 34, "pregnancy": false, "allergies": []},
      "items": [
        {"drug_name":"Panadol 500mg","active_ingredient":"paracetamol","strength":"500mg","dosage_form":"viên nén","quantity":20,"dosage_instruction":"1 viên x 3 lần/ngày sau ăn"},
        {"drug_name":"Amoxicillin 500mg","active_ingredient":"amoxicillin","strength":"500mg","dosage_form":"viên nang","quantity":21,"dosage_instruction":"1 viên x 3 lần/ngày"},
        {"drug_name":"Bromhexin 8mg","active_ingredient":"bromhexine","strength":"8mg","dosage_form":"viên nén","quantity":30,"dosage_instruction":"1 viên x 3 lần/ngày"}
      ]
    }' | $JQ
}

# Kịch bản 2 — đơn thuốc có thuốc KHÔNG KINH DOANH (Cefixime chẳng hạn).
rx_not_carried() {
  hr "POST $API/prescriptions/check — item không kinh doanh"
  curl -fsS -X POST "$API/prescriptions/check" \
    -H 'content-type: application/json' \
    -d '{
      "patient": {"age_years": 45, "pregnancy": false, "allergies": ["penicillin"]},
      "items": [
        {"drug_name":"Cefixime 200mg","active_ingredient":"cefixime","strength":"200mg","dosage_form":"viên nang","quantity":10}
      ]
    }' | $JQ
}

# Kịch bản 3 — dùng file examples/rx_example.json.
rx_from_file() {
  hr "POST $API/prescriptions/check — từ file examples/rx_example.json"
  curl -fsS -X POST "$API/prescriptions/check" \
    -H 'content-type: application/json' \
    -d @"$(dirname "$0")/rx_example.json" | $JQ
}

# Kịch bản 3b — Panadol hết hàng (seed mặc định) + brand paracetamol không kinh doanh.
# Kỳ vọng: cả 2 item trả về substitutes theo hoạt chất paracetamol
# (Hapacol 500, Efferalgan 500mg, Panadol Extra, Tiffy Dey, Decolgen Forte...),
# lọc chỉ thuốc đang có tồn kho.
rx_paracetamol_oos() {
  hr "POST $API/prescriptions/check — Panadol hết + brand lạ (substitutes theo paracetamol)"
  curl -fsS -X POST "$API/prescriptions/check" \
    -H 'content-type: application/json' \
    -d @"$(dirname "$0")/rx_paracetamol_oos.json" | $JQ
}

# Helper: đặt tồn kho Panadol (SKU-001) về 0 — trùng seed mặc định.
# Dùng sau khi đã chạy panadol_restore (hoặc tự tăng kho) để quay về trạng thái demo.
panadol_set_oos() {
  hr "SQL: SET qty_on_hand = 0 cho SKU-001 (Panadol 500mg)"
  psql_exec "UPDATE inventory SET qty_on_hand = 0, updated_at = now()
             WHERE product_id = (SELECT id FROM products WHERE sku = 'SKU-001');"
}

# Helper: đổi tồn kho Panadol sang 120 để minh hoạ trạng thái còn hàng.
panadol_restore() {
  hr "SQL: SET qty_on_hand = 120 cho SKU-001 (Panadol 500mg)"
  psql_exec "UPDATE inventory SET qty_on_hand = 120, updated_at = now()
             WHERE product_id = (SELECT id FROM products WHERE sku = 'SKU-001');"
}

# Kịch bản 3c — CURL INLINE (không cần file) cho đơn chỉ kê Panadol 500mg.
# Với seed mặc định, Panadol đang OOS -> response sẽ có substitutes paracetamol.
# Gọi panadol_restore trước nếu muốn thấy trạng thái in_stock.
rx_panadol_only() {
  hr "POST $API/prescriptions/check — chỉ Panadol 500mg (inline curl)"
  curl -fsS -X POST "$API/prescriptions/check" \
    -H 'content-type: application/json' \
    -d @- <<'JSON' | $JQ
{
  "patient": {
    "age_years": 34,
    "pregnancy": false,
    "allergies": []
  },
  "items": [
    {
      "drug_name": "Panadol 500mg",
      "active_ingredient": "paracetamol",
      "strength": "500mg",
      "dosage_form": "viên nén",
      "quantity": 20,
      "dosage_instruction": "1 viên x 3 lần/ngày khi sốt"
    }
  ]
}
JSON
}

# Kịch bản 3d — FULL FLOW demo cả 2 trạng thái Panadol, trả về seed default.
# 1) rx_panadol_only  (seed=OOS -> expect out_of_stock + substitutes paracetamol)
# 2) panadol_restore  (qty=120)
# 3) rx_panadol_only  (expect in_stock, không substitutes)
# 4) panadol_set_oos  (qty=0, về lại seed default)
rx_panadol_oos_scenario() {
  rx_panadol_only
  panadol_restore
  rx_panadol_only
  panadol_set_oos
}

# Kịch bản 4 — cảm cúm người lớn (không red flag) -> kỳ vọng F-FLU-ADULT top hit.
sym_flu_adult() {
  hr "POST $API/symptoms/advise — cảm cúm người lớn"
  curl -fsS -X POST "$API/symptoms/advise" \
    -H 'content-type: application/json' \
    -d '{
      "patient": {"age_years": 28, "pregnancy": false, "allergies": []},
      "symptoms_vi": ["sốt nhẹ", "sổ mũi", "đau họng"],
      "duration_days": 1
    }' | $JQ
}

# Kịch bản 5 — trẻ 2 tháng sốt -> red_flags không rỗng, suggestions rỗng.
sym_infant_fever() {
  hr "POST $API/symptoms/advise — trẻ 2 tháng sốt (red flag)"
  curl -fsS -X POST "$API/symptoms/advise" \
    -H 'content-type: application/json' \
    -d '{
      "patient": {"age_years": 0.17, "pregnancy": false, "allergies": []},
      "symptoms_vi": ["sốt"],
      "duration_days": 1
    }' | $JQ
}

# Kịch bản 6 — phụ nữ có thai với triệu chứng sổ mũi -> red flag nhắc đi khám.
sym_pregnancy() {
  hr "POST $API/symptoms/advise — phụ nữ có thai"
  curl -fsS -X POST "$API/symptoms/advise" \
    -H 'content-type: application/json' \
    -d '{
      "patient": {"age_years": 30, "pregnancy": true, "allergies": []},
      "symptoms_vi": ["sổ mũi", "hắt hơi"],
      "duration_days": 2
    }' | $JQ
}

# Kịch bản 7 — tiêu chảy nhẹ người lớn -> kỳ vọng F-DIARRHEA-MILD (ORS + Smecta).
sym_diarrhea() {
  hr "POST $API/symptoms/advise — tiêu chảy nhẹ người lớn"
  curl -fsS -X POST "$API/symptoms/advise" \
    -H 'content-type: application/json' \
    -d '{
      "patient": {"age_years": 35, "pregnancy": false, "allergies": []},
      "symptoms_vi": ["tiêu chảy", "đau bụng nhẹ"],
      "duration_days": 1
    }' | $JQ
}

# Kịch bản 8 — khó thở + đau ngực (cấp cứu) -> red flags.
sym_redflag_dyspnea() {
  hr "POST $API/symptoms/advise — khó thở (red flag)"
  curl -fsS -X POST "$API/symptoms/advise" \
    -H 'content-type: application/json' \
    -d '{
      "patient": {"age_years": 55, "pregnancy": false, "allergies": []},
      "symptoms_vi": ["khó thở", "đau ngực"],
      "duration_days": 0
    }' | $JQ
}

ALL=(healthz readyz rx_mixed rx_not_carried rx_from_file rx_paracetamol_oos rx_panadol_only rx_panadol_oos_scenario sym_flu_adult sym_infant_fever sym_pregnancy sym_diarrhea sym_redflag_dyspnea)

if [[ $# -eq 0 ]]; then
  for fn in "${ALL[@]}"; do "$fn"; done
else
  for fn in "$@"; do "$fn"; done
fi
