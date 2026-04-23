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

hr() { printf '\n--- %s ---\n' "$1"; }

healthz() {
  hr "GET $API/healthz"
  curl -fsS "$API/healthz" | $JQ
}

readyz() {
  hr "GET $API/readyz"
  curl -fsS "$API/readyz" | $JQ
}

# Kịch bản 1 — đơn thuốc 3 item, 1 item hết hàng (Bromhexin 8mg, SKU-014 qty=0).
# Kỳ vọng: Panadol in_stock, Amoxicillin in_stock (rx_only), Bromhexin out_of_stock
# -> gợi ý thay thế Ambroxol 30mg.
rx_mixed() {
  hr "POST $API/prescriptions/check — đơn 3 item (1 hết hàng)"
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

# Kịch bản 3b — Panadol hết hàng + brand paracetamol không kinh doanh.
# Kỳ vọng: cả 2 item trả về substitutes theo hoạt chất paracetamol
# (Hapacol 500, Efferalgan 500mg, Panadol Extra, Tiffy Dey, Decolgen Forte...),
# lọc chỉ thuốc đang có tồn kho.
# LƯU Ý: trước khi chạy, SET qty_on_hand = 0 cho SKU-001 (Panadol) trong inventory
# để tạo trạng thái out_of_stock cho demo.
rx_paracetamol_oos() {
  hr "POST $API/prescriptions/check — Panadol hết + brand lạ (substitutes theo paracetamol)"
  curl -fsS -X POST "$API/prescriptions/check" \
    -H 'content-type: application/json' \
    -d @"$(dirname "$0")/rx_paracetamol_oos.json" | $JQ
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

ALL=(healthz readyz rx_mixed rx_not_carried rx_from_file rx_paracetamol_oos sym_flu_adult sym_infant_fever sym_pregnancy sym_diarrhea sym_redflag_dyspnea)

if [[ $# -eq 0 ]]; then
  for fn in "${ALL[@]}"; do "$fn"; done
else
  for fn in "$@"; do "$fn"; done
fi
