## v0.7.0 Custom Curve Profile 계획

### 목표

현재 하드코딩된 `BASIC_MOLDING`, `DOUBLE_TRIM` 대신 사용자가 직접 그린 별도의 Curve를 벽 단면으로 사용할 수 있게 합니다.

```text
Wall Path Curve ── 벽의 평면 경로
Profile Curve   ── 벽의 세로 단면 형태
                      ↓
               기존 Mesh Builder
```

기존 Preset 방식은 그대로 유지하며 새 `.blend`와 기존 파일 모두 기본적으로 Preset 모드를 사용합니다.

### 1. UI 구성

Geometry 영역의 Profile 설정을 다음처럼 변경합니다.

- `Profile Source`
  - `Preset`
  - `Custom Curve`
- Preset일 때
  - 기존 `Preset` 메뉴 표시
- Custom Curve일 때
  - Profile Curve 오브젝트 선택
  - `Create Profile Template`
  - `Edit Profile`
  - `Validate Profile`
  - `Profile Resolution`
- 축 안내
  - 로컬 X축: 벽에서 돌출되는 Offset
  - 로컬 Y축: 벽 높이
  - Profile 오브젝트의 위치와 회전은 무시

벽 경로의 Bezier Resolution과 혼동되지 않도록 기존 옵션 이름은 `Path Resolution`로 변경하는 것이 좋습니다.

### 2. Profile Curve 제작 규칙

권장 규칙은 다음과 같습니다.

- `POLY`와 `BEZIER` 지원
- 닫히지 않은 Open Spline만 허용
- 아래에서 위로 연결된 하나의 단면 체인
- 수직 방향이 반대면 자동으로 뒤집기
- 높이가 다시 아래로 내려가는 단면은 오류 처리
- Profile의 가장 낮은 Y를 자동으로 높이 0으로 정규화
- X=0을 벽 기준선으로 사용
- Object Scale X/Y는 반영하고 위치·회전은 무시

NURBS, 닫힌 단면, 분기된 단면은 v0.7.0 범위에서 제외합니다.

### 3. Body/Trim 구간 지정

Custom Profile에서도 Body와 Trim 재질 구분이 필요합니다. 가장 현실적인 방식은 연결된 여러 Profile Spline을 사용하는 것입니다.

- Profile Curve에 태그용 재질 슬롯 생성
  - `PWG_Profile_Body`
  - `PWG_Profile_Trim`
- 각 Spline의 Material Index로 Body/Trim 구분
- 서로 맞닿은 Spline을 아래에서 위로 자동 연결
- 실제 생성 벽에는 기존 `PWG_Body`, `PWG_Trim` 재질 적용
- Top과 Section 재질은 현재 방식 유지

`Create Profile Template` 버튼으로 Body와 상·하단 Trim이 지정된 기본 단면을 만들어주면 사용자가 Blender의 Curve Edit Mode에서 바로 형태를 바꿀 수 있습니다.

### 4. 내부 구조

새로운 `profile_utils.py`를 추가하는 구성이 좋습니다.

담당 기능:

- Custom Profile Curve 샘플링
- 로컬 X/Y를 `(z, offset, material_key)` 형식으로 변환
- 여러 Spline 연결 순서 결정
- 방향 자동 반전
- Body/Trim 태그 해석
- 중복 점 병합 및 유효성 검사

`mesh_builder.py`는 Preset인지 Custom인지 알 필요 없이 최종 Profile 배열만 받게 유지합니다. 이렇게 해야 현재 UV, Top Trim, Section, Fill Inside 로직을 재사용할 수 있습니다.

### 5. 기존 Scale 옵션 처리

권장 동작:

- `Height Scale`: Custom Profile 전체 높이에 적용
- `Offset Scale`: 돌출 깊이에 적용
- `Bottom/Top Trim Scale`: Custom 모드에서는 기본적으로 적용하지 않음
- 필요하면 `Apply Trim Scales` 옵션을 별도로 제공

직접 그린 단면에 현재 기본값 `0.25`가 자동 적용되면 사용자가 그린 형태와 달라질 수 있기 때문입니다.

### 6. Auto Update 연결

Custom Profile Curve 편집도 현재 80ms 디바운서에 연결합니다.

- Profile Curve가 변경되면 이를 사용하는 모든 Wall Source 검색
- 여러 벽이 같은 Profile을 공유할 수 있음
- 각 Wall Source는 대기열에 한 번만 등록
- Profile 삭제 시 Preset으로 몰래 전환하지 않고 명확한 경고 표시
- Profile 이름 변경은 PointerProperty로 안전하게 추적

### 7. 구현 순서

1. `Profile Source` 속성과 PointerProperty 추가
2. `profile_utils.py` 추출·검증기 구현
3. Preset/Profile 공통 데이터 구조로 Mesh Builder 연결
4. Body/Trim Spline 태그 처리
5. Template 생성·Edit·Validate UI 추가
6. Profile Curve 변경 Auto Update 연결
7. 저장·리로드·삭제·복제 안정성 검증
8. 전체 회귀 테스트

### 8. 필수 테스트

- POLY/BEZIER Profile 추출
- 역방향 Profile 자동 반전
- Body/Trim 구간과 재질 인덱스
- Preset과 Custom 전환
- Fill Inside, Section, Top Trim 조합
- Profile Edit Mode Auto Update
- 하나의 Profile을 공유하는 여러 벽
- Profile 삭제·이름 변경·복제
- 잘못된 Closed/Disconnected Profile 오류 메시지
- 기존 `.blend` 파일 호환
- 기존 11개 회귀 테스트

`v0.7.0`에서는 Custom Profile 생성과 편집 안정성까지만 다루고, Groove·Opening·닫힌 단면 Sweep 등은 별도 버전으로 분리하는 것을 권장합니다.