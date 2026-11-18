# Tool 정의서

> `python scripts/gen_tool_spec.py` 로 생성한 문서입니다. 직접 고치지 말고 `backend/tools/__init__.py` 를 고친 뒤 다시 생성하세요.

## 공통 응답 형식

```json
{"ok": true, "data": {...}, "meta": {"tool": "이름", "elapsed_ms": 12.3}}
{"ok": false, "error": {"code": "INVALID_KEY", "message": "..."}, "meta": {...}}
```

Tool 은 예외를 밖으로 던지지 않습니다. 외부 API 오류 원문(키가 든 URL 포함)은 메시지에 넣지 않습니다.

## 실패 코드

| 코드 | 재계획 대상 |
| --- | --- |
| BAD_ARGUMENT | 아니오 (다시 해도 같음) |
| INVALID_KEY | 아니오 (다시 해도 같음) |
| NOT_FOUND | 예 |
| NO_DATA | 예 |
| UPSTREAM_ERROR | 예 |
| NOT_IMPLEMENTED | 아니오 (다시 해도 같음) |
| NO_PLACE | 예 |
| NO_COORD | 예 |
| CLOSED | 예 |
| NO_HOURS | 예 |
| NO_SERVICE | 예 |
| AMBIGUOUS_STATION | 예 |
| QUOTA_EXCEEDED | 아니오 (다시 해도 같음) |
| NO_INDEX | 예 |

## Tool 목록

### search_heritage

- 언제 쓰나: 여행 지역에서 국보·보물·사적 후보가 필요할 때 부른다. 좌표가 함께 온다.
- 종류: 외부 API 툴
- 요구사항: F3002
- 필수 인자: region

```json
{
  "type": "object",
  "properties": {
    "region": {
      "type": "string",
      "description": "시도 이름 (예: 경북)"
    },
    "kind": {
      "type": "string",
      "enum": [
        "국보",
        "보물",
        "사적"
      ]
    },
    "limit": {
      "type": "integer"
    }
  },
  "required": [
    "region"
  ]
}
```

### search_tour

- 언제 쓰나: 어떤 지점 주변의 관광지·문화시설·축제·음식점·숙박 후보가 필요할 때 부른다.
- 종류: 외부 API 툴
- 요구사항: F3002
- 필수 인자: lat, lon

```json
{
  "type": "object",
  "properties": {
    "lat": {
      "type": "number"
    },
    "lon": {
      "type": "number"
    },
    "kind": {
      "type": "string",
      "enum": [
        "attraction",
        "culture",
        "festival",
        "restaurant",
        "lodging"
      ]
    },
    "radius_m": {
      "type": "integer"
    }
  },
  "required": [
    "lat",
    "lon"
  ]
}
```

### search_place

- 언제 쓰나: TourAPI 에 없는 카페나 음식점을 동선 근처에서 보충해야 할 때 부른다. 영업시간은 주지 않는다.
- 종류: 외부 API 툴
- 요구사항: F3002
- 필수 인자: lat, lon

```json
{
  "type": "object",
  "properties": {
    "lat": {
      "type": "number"
    },
    "lon": {
      "type": "number"
    },
    "kind": {
      "type": "string",
      "enum": [
        "cafe",
        "restaurant",
        "attraction",
        "culture"
      ]
    },
    "radius_m": {
      "type": "integer"
    }
  },
  "required": [
    "lat",
    "lon"
  ]
}
```

### get_visit_info

- 언제 쓰나: 후보 장소의 관람·영업시간, 쉬는 날, 입장료를 확인해 방문 가능 여부를 판정해야 할 때 부른다.
- 종류: 외부 API 툴
- 요구사항: F3003
- 필수 인자: content_id

```json
{
  "type": "object",
  "properties": {
    "content_id": {
      "type": "string"
    },
    "kind": {
      "type": "string",
      "enum": [
        "attraction",
        "culture",
        "festival",
        "restaurant",
        "lodging"
      ]
    }
  },
  "required": [
    "content_id"
  ]
}
```

### plan_leg

- 언제 쓰나: 두 지점 사이를 사용자가 고른 이동 수단으로 언제 어디서 타고 얼마나 걸리는지 알아야 할 때 부른다.
- 종류: 외부 API 툴
- 요구사항: F3004
- 필수 인자: mode, origin, destination

```json
{
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "train",
        "express",
        "intercity",
        "car",
        "transit"
      ]
    },
    "origin": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string"
        },
        "lat": {
          "type": "number"
        },
        "lon": {
          "type": "number"
        }
      }
    },
    "destination": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string"
        },
        "lat": {
          "type": "number"
        },
        "lon": {
          "type": "number"
        }
      }
    },
    "date": {
      "type": "string",
      "description": "YYYY-MM-DD"
    },
    "depart_after": {
      "type": "string",
      "description": "HH:MM"
    }
  },
  "required": [
    "mode",
    "origin",
    "destination"
  ]
}
```

### get_weather

- 언제 쓰나: 여행 날짜·지역의 강수확률과 기온으로 야외·실내 비중을 정해야 할 때 부른다.
- 종류: 외부 API 툴
- 요구사항: F3004
- 필수 인자: lat, lon, date

```json
{
  "type": "object",
  "properties": {
    "lat": {
      "type": "number"
    },
    "lon": {
      "type": "number"
    },
    "date": {
      "type": "string"
    }
  },
  "required": [
    "lat",
    "lon",
    "date"
  ]
}
```

### get_holidays

- 언제 쓰나: 여행 날짜가 공휴일인지 알아야 할 때(휴관일 판정) 부른다.
- 종류: 외부 API 툴
- 요구사항: F3004
- 필수 인자: year, month

```json
{
  "type": "object",
  "properties": {
    "year": {
      "type": "integer"
    },
    "month": {
      "type": "integer"
    }
  },
  "required": [
    "year",
    "month"
  ]
}
```

### get_crowd

- 언제 쓰나: 관광지가 붐비는 시간대를 피해 방문 순서를 정해야 할 때 부른다.
- 종류: 외부 API 툴
- 요구사항: F3004
- 필수 인자: area_code, date

```json
{
  "type": "object",
  "properties": {
    "area_code": {
      "type": "string"
    },
    "date": {
      "type": "string"
    }
  },
  "required": [
    "area_code",
    "date"
  ]
}
```

### get_videos

- 언제 쓰나: 일정에 들어간 장소의 참고 영상을 보여 줄 때 부른다. 판단 근거로 쓰지 않는다.
- 종류: 외부 API 툴
- 요구사항: content
- 필수 인자: query

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string"
    },
    "max_results": {
      "type": "integer"
    }
  },
  "required": [
    "query"
  ]
}
```

### make_insta_links

- 언제 쓰나: 일정의 장소·지역 Instagram 해시태그 링크를 붙일 때 부른다.
- 종류: 로컬 서버 툴
- 요구사항: content
- 필수 인자: place_names

```json
{
  "type": "object",
  "properties": {
    "place_names": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "region": {
      "type": "string"
    }
  },
  "required": [
    "place_names"
  ]
}
```

### ask_heritage

- 언제 쓰나: 국가유산에 대한 설명·역사·지정 이유를 근거와 함께 답해야 할 때 부른다.
- 종류: 로컬 서버 툴
- 요구사항: F3022
- 필수 인자: question

```json
{
  "type": "object",
  "properties": {
    "question": {
      "type": "string"
    }
  },
  "required": [
    "question"
  ]
}
```
