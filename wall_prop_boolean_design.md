# 애드온 기획서: Wall & Prop Line Boolean Tool

## 1. 개요 (Overview)
본 애드온은 2D 형태의 라인 오브젝트(Wall, Prop)를 결합하여, Prop이 위치한 영역만큼 Wall의 라인을 제거하고 자연스럽게 뚫린 공간(문, 창문, 통로 등)을 생성하는 자동화 모델링 툴입니다. 기존의 단순 1D 선분 교차 방식의 한계를 극복하기 위해 오브젝트에 두께를 주어 면/입체로 만든 뒤 Boolean 연산을 수행하는 방식을 채택합니다.

## 2. 핵심 목표 (Core Objectives)
- **정확성**: 복잡한 각도나 겹침 상태에서도 오류 없이 Wall에 Prop 형태의 공간을 생성.
- **안정성**: 단순 선분 교차(Intersection) 오류를 피하기 위해 두께(Double Line) 기반의 기하학적(Geometry) Boolean 방식을 사용.
- **자동화**: 사용자가 Wall과 Prop을 선택하고 버튼을 누르면 내부적으로 [2중 라인 생성 -> Boolean -> 외곽선 추출] 과정이 한 번에 처리됨.

## 3. 작동 원리 및 세부 로직 (Workflow & Logic)
제안해주신 아이디어를 기반으로 한 핵심 알고리즘 단계입니다:

### Step 1: 2중 라인 생성 (Offset / Solidify)
- **Wall**과 **Prop** 라인 오브젝트 각각의 법선(Normal) 바깥 방향으로 선을 복제/밀어내기(Offset)하여 2중 라인을 만듭니다.
- 이 2중 라인의 양 끝을 닫아(Close) 두께를 가진 **단일 면(Polygon) 또는 3D 입체(Solid)** 형태로 변환합니다.

### Step 2: Boolean 연산 수행 (Union)
- 면(또는 입체)으로 변환된 Wall과 Prop 오브젝트에 대해 **Boolean 합집합(Union)** 연산을 수행합니다.
- Union 연산을 거치면 Wall과 Prop이 겹치는 내부 영역의 선분(교차점 안쪽 라인들)이 수학적으로 완벽히 병합되어 제거됩니다.

### Step 3: 외곽선 추출 및 정리 (Boundary Extraction)
- Boolean Union이 완료된 결과물에서 **외곽선(Boundary Edges)만 다시 추출**합니다.
- 이 과정을 통해 사용자가 의도한 대로 Wall 라인 중 Prop과 겹쳤던 부분이 사라지고, Wall 내부 방향으로 뻗어 있던 Prop의 잉여 라인들도 제거된 깔끔한 단일 형태의 외곽선(Single Line Outline)이 완성됩니다.

## 4. UI/UX 구성 (User Interface)
블렌더 우측 툴 패널 (N-Panel)에 다음과 같은 직관적인 UI를 제공합니다.
- **Target Wall**: 메인이 되는 벽체 라인 오브젝트 선택란.
- **Target Prop**: 벽에 합성될 프랍 라인 오브젝트 선택란.
- **Line Thickness (두께)**: 2중 라인(Offset)을 생성할 때 적용할 바깥 방향 두께 값 설정.
- **Execute Boolean**: 위 로직을 실행하는 메인 오퍼레이터 버튼.

## 5. 개발 시 고려 및 제한 사항 (Considerations)
- **방향성(Normal) 판단**: '바깥 방향'으로 정확히 2중 라인을 치기 위해 각 라인의 방향(시계/반시계 또는 3D Normal)을 정확히 계산하는 로직이 필요합니다.
- **오픈/클로즈 라인 처리**: Wall이나 Prop이 닫힌 곡선(Closed Loop)인지 열린 곡선(Open Line)인지에 따라 2중 라인을 생성할 때 끝단을 막아주는(Cap) 추가 처리가 필요합니다.
