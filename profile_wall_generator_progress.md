# Profile Wall Generator 구현 진행 기록

작성일: 2026-06-23

## 현재 상태

`profile_wall_generator` 애드온의 1차 MVP를 구현했다.

위치:

```text
C:\Users\user\AppData\Roaming\Blender Foundation\Blender\5.1\scripts\addons\profile_wall_generator
```

Blender UI 위치:

```text
View3D > Sidebar(N) > K-Quick Tools > Profile Wall Generator
```

---

## 구현된 파일

```text
profile_wall_generator/
├── __init__.py
├── properties.py
├── operators.py
├── panels.py
├── profile_presets.py
├── path_utils.py
├── mesh_builder.py
├── material_utils.py
└── uv_utils.py
```

---

## 구현된 기능

### 애드온 기본 구조

- Blender 5.1용 애드온 등록/해제
- `K-Quick Tools` 탭에 UI 패널 추가
- Scene PropertyGroup 기반 설정값 관리

### 입력 경로 처리

- Curve Poly Spline 입력 지원
- Curve Bezier Spline 입력 지원
  - 내부에서 일정 해상도로 샘플링
- Mesh Edge Chain 입력 지원
- 열린 경로 / 닫힌 경로 대응
- 너무 가까운 중복 포인트 제거
- 닫힌 경로의 winding order 기반 외부 방향 계산
- `Flip Direction` 옵션으로 몰딩 방향 반전 가능

### 프로파일 벽 생성

- 커브 1줄을 따라 세로 단면 프로파일을 연결해 메시 생성
- 기본 프리셋:
  - `Basic Molding`
  - `Double Trim`
- 프로파일 형식:

```python
(z, offset, material_key)
```

- `z`: 벽 높이 방향 위치
- `offset`: 기준 벽면에서 몰딩이 돌출되는 거리
- `material_key`: `body`, `trim`, `cap`

### 재질 처리

- Body / Trim 재질 슬롯 자동 구성
- 사용자가 지정한 재질이 있으면 해당 재질 사용
- 지정하지 않으면 기본 재질 자동 생성
  - `PWG_Body`
  - `PWG_Trim`
- 열린 커브 cap 면은 Body 재질 사용
- `body -> trim`, `trim -> body` 전환 구간은 Trim 재질 사용
  - 상단 몰딩 꺾이는 부분에 Body 재질이 들어가던 문제 수정 완료

### UV 처리

- 기본 UV Map 자동 생성
- UV 이름:

```text
ProfileWallUV
```

- 기본 방식:

```text
U = 경로 시작점부터의 누적 거리
V = 프로파일 z 높이
```

- UI에서 `U Scale`, `V Scale` 조정 가능

### 벽 두께 처리

- 생성된 프로파일 표면에 Solidify Modifier 자동 추가
- Modifier 이름:

```text
PWG Wall Thickness
```

- `Wall Thickness` 파라미터 연결
- `Thickness Direction` 지원
  - Outside
  - Inside
  - Center
- Solidify Mode 기본값을 `Complex`로 설정
  - Blender Python 값: `NON_MANIFOLD`

### 원본 커브 숨김 처리

- `Hide Source Curve` 옵션 구현
- 기존 방식:

```python
source_obj.hide_viewport = True
```

- 현재 방식:

```python
source_obj.hide_set(True)
```

- 즉, Outliner의 `Disable in Viewports`가 아니라 `Hide in Viewport` 방식으로 숨긴다.

### Update / Convert

- `Generate Wall`
  - 활성 Curve/Mesh 라인에서 새 프로파일 벽 생성
- `Update Wall`
  - 생성된 벽이 원본 커브 이름을 기억하고 다시 생성
- `Edit Source Curve`
  - 생성된 Mesh를 숨기고 원본 Curve를 표시/선택
- `Show Generated Mesh`
  - 원본 Curve를 숨기고 생성된 Mesh를 표시/선택
- `Convert To Editable Mesh`
  - 원본 커브 연결 커스텀 속성 제거
  - 선택 옵션으로 Modifier Apply 가능

---

## UI 파라미터

### Wall

- `Preset`
- `Wall Thickness`
- `Thickness Direction`
- `Height Scale`
- `Offset Scale`
- `Flip Direction`

### Material

- `Body`
- `Trim`

### UV

- `U Scale`
- `V Scale`

### Options

- `Cap Ends`
- `Hide Source Curve`
- `Merge Distance`
- `Add Bevel`
- `Bevel Width`

---

## 검증 완료 항목

Blender 5.1.1 백그라운드 테스트로 다음을 확인했다.

```text
애드온 register/unregister 성공
닫힌 사각형 Poly Curve Generate 성공
열린 ㄱ자 Poly Curve Generate 성공
Update Wall 성공
UV Layer 생성 확인
Solidify Modifier 생성 확인
Solidify Mode = NON_MANIFOLD 확인
원본 커브 hide_set(True) 적용 확인
hide_viewport는 False 유지 확인
상단 trim 전환 구간 material index 수정 확인
Generate -> Edit Source Curve -> Show Generated Mesh 전환 확인
Curve 선택 상태에서 Update 시 기존 Mesh 교체 확인
```

Python 문법 검사:

```text
profile_wall_generator/*.py py_compile 통과
```

---

## 최근 수정 내역

### 1. 상단 몰딩 전환부 재질 문제 수정

문제:

- 하단 Trim은 정상
- 상단 몰딩이 시작되는 꺾이는 면에 Trim Material이 들어가지 않음

원인:

- 프로파일 구간 재질을 아래쪽 포인트 기준으로 지정하고 있었음
- `body -> trim` 전환 구간이 Body 재질로 처리됨

수정:

- 구간 양쪽 중 하나라도 `trim`이면 해당 face를 Trim 재질로 처리

### 2. 원본 커브 숨김 방식 변경

문제:

- 원본 커브를 숨길 때 `Disable in Viewports` 방식으로 꺼짐

수정:

- `hide_viewport = True` 대신 `hide_set(True)` 사용
- Outliner의 눈 아이콘 숨김 방식으로 변경

### 3. Solidify Mode 기본값 변경

요청:

- Solidify Modifier의 Mode 기본값을 `Complex`로 설정

수정:

- `modifier.solidify_mode = "NON_MANIFOLD"` 추가

### 4. Curve / Mesh 전환 버튼 추가

요청:

- 벽 생성 후 원본 Curve를 다시 켜고 선택하는 과정이 번거로움
- 버튼 하나로 Mesh를 숨기고 Curve만 표시되게 하고 싶음

수정:

- `Edit Source Curve` 버튼 추가
- `Show Generated Mesh` 버튼 추가
- 생성 시 원본 Curve에도 생성 Mesh 이름을 저장
- Curve 선택 상태에서 `Update Wall`을 누르면 기존 Mesh를 찾아 삭제 후 재생성

### 5. Miter 코너 알고리즘 및 Miter Limit 추가

요청:

- 예각 코너에서 몰딩 두께가 얇아지거나 면이 교차하는 문제 해결

수정:

- `path_utils.py`에서 두 세그먼트의 Normal 내적을 이용해 Miter Factor를 계산하도록 수정
- `mesh_builder.py`에서 정점 계산 시 offset 거리에 Miter Factor를 곱하여 두께 일정 유지
- `properties.py` 및 `panels.py`에 `Miter Limit` 파라미터를 추가하여 지나친 스파이크(Spike) 발생 방지 (기본값 3.0)

---

## 아직 남은 작업

### 우선순위 높음

- 실제 Blender UI에서 다양한 커브로 수동 검증
- Update 시 원본 커브가 숨겨진 상태에서도 쉽게 선택/갱신하는 UX 개선

### 우선순위 중간

- Bezier 샘플링 해상도 UI 옵션 추가
- 프로파일별 material key 확장
- Body와 Trim의 UV scale 분리
- Bevel Modifier 옵션 품질 확인
- Convert To Editable Mesh UI에서 Apply Modifier 옵션 노출 개선

### 우선순위 낮음

- 프리셋 외부 JSON 저장
- 평지붕 / 박공지붕 모듈
- Prop 홈(groove) 모듈
- 문 / 창문 컷아웃
- Unity 6 내보내기 전용 정리 버튼

---

## 현재 한계

- 코너는 아직 단순 평균 normal 방식이다.
- 날카로운 코너에서는 몰딩이 찌그러지거나 겹칠 수 있다.
- Solidify는 Modifier 기반이므로 Unity 내보내기 전에 Apply가 필요할 수 있다.
- UV는 기본적인 거리/높이 기반이며, 몰딩 단면의 실제 둘레 길이를 따라 펴는 고급 UV는 아직 아니다.
- Update는 원본 오브젝트 이름을 기준으로 찾기 때문에, 원본 커브 이름을 바꾸면 연결이 끊길 수 있다.

---

## 다음 추천 작업

1. Blender에서 실제 작업용 커브로 생성 테스트
2. 문제가 보이는 코너 스크린샷 수집
3. Miter 코너 처리 구현
4. Update UX 개선
5. Unity 6로 임시 Export 후 재질/노멀/UV 확인
