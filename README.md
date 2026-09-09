# Profile Wall Generator 사용자 가이드

**Profile Wall Generator**는 Blender 5.1+에서 Curve 또는 Mesh 경로를 따라 프로파일 벽을 생성하는 애드온입니다. 벽의 몸통과 몰딩을 서로 다른 재질로 지정할 수 있고, 원본 경로를 수정한 뒤 벽을 다시 생성할 수 있습니다.

## 설치 및 패널 열기

애드온을 설치하고 활성화한 뒤 3D Viewport에서 `N` 키를 눌러 사이드바를 엽니다. **K-Quick Tools** 탭의 **Profile Wall Generator** 패널을 사용합니다.

## 권장 작업 순서

1. 벽의 기준이 될 **Curve**를 만들고 선택합니다. 일반적인 벽 경로에는 Curve를 권장합니다.
2. Curve 데이터에서 필요한 스플라인을 편집합니다. `POLY`와 `BEZIER` 스플라인을 지원하며, 한 Curve 오브젝트 안의 여러 스플라인도 각각 경로로 처리합니다. `NURBS` 스플라인은 지원하지 않습니다.
3. 패널에서 프로파일과 벽 설정을 지정하고 **Generate Wall**을 누릅니다.
4. 원본을 다시 편집하려면 생성된 벽을 선택한 뒤 상단 액션 영역의 **Edit Source Curve**를 누릅니다. 편집을 끝내고 **Show Generated Mesh**를 누르면 Object Mode로 돌아가 벽을 선택하고, Auto Update가 켜져 있으면 대기 중인 업데이트도 반영합니다.
5. 연결을 끊고 일반 메쉬로 마무리하려면 생성된 벽에서 **Convert To Editable Mesh**를 누릅니다. 필요하면 표시되는 옵션에서 모디파이어 적용 여부를 선택합니다.

### Mesh 경로를 사용할 때

Mesh는 하나의 연결된 선형 경로만 지원합니다. 즉, 분기 없는 하나의 열린 체인 또는 하나의 닫힌 루프여야 합니다. 여러 조각으로 분리된 선, 분기된 경로, 연결되지 않은 여러 경로는 사용할 수 없습니다. 가능하면 여러 경로가 필요한 작업은 여러 스플라인을 가진 Curve 하나로 구성하세요.

Mesh Line은 Auto Update를 켜도 Edit Mode에서 편집한 결과가 모드를 나간 뒤 벽에 반영됩니다. 편집 중 벽을 확인하려면 Curve를 사용하세요.

## 패널과 설정

원본 Curve 또는 Mesh를 선택하면 해당 원본에 저장된 설정이 표시됩니다. 생성된 벽을 선택해도 연결된 원본의 설정을 편집합니다. 패널 상단에는 상황에 따라 다음 버튼이 표시됩니다.

- **Generate Wall**: 선택한 원본으로 새 벽을 생성합니다.
- **Update Wall**: 원본과 연결된 벽을 현재 설정으로 다시 생성합니다.
- **Edit Source Curve**: 원본을 표시하고 Edit Mode로 들어갑니다. Auto Update가 켜져 있으면 편집 중 벽을 함께 표시합니다.
- **Show Generated Mesh**: Edit Mode를 종료하고 생성된 벽만 선택합니다. 원본은 Hide Source가 켜져 있을 때 숨깁니다.
- **Convert To Editable Mesh**: 벽과 원본의 연결을 제거해 일반 편집 가능한 메쉬로 만듭니다.

### Geometry

- **Preset**: 현재 제공되는 `Basic Molding`, `Double Trim` 두 프로파일 중 선택합니다. Custom Curve Profile은 아직 제공하지 않습니다.
- **Height Scale**: 벽 높이를 조절합니다.
- **Bottom Trim Scale / Top Trim Scale**: 아래·위 몰딩의 높이를 조절합니다.
- **Offset Scale**: 프로파일의 돌출·홈 깊이를 조절합니다.
- **Flip Direction**: 프로파일 오프셋 방향을 뒤집습니다.
- **Wall Thickness**: Hollow 또는 Section 벽의 두께를 지정합니다. 두께가 0이면 단면 벽이 생성됩니다.
- **Direction**: 두께를 `Outside`, `Inside`, `Center` 중 어느 방향으로 만들지 지정합니다.
- **Flat Inner Face**: 두께가 있는 벽의 안쪽 면을 평평하게 유지합니다.

### Interior

- **Hollow**: 닫히지 않은 경로는 벽을 만들고, 닫힌 경로는 내부 바닥 없이 속이 빈 벽을 만듭니다.
- **Section**: 닫힌 경로에 내부 바닥(Section)을 추가합니다. `Section Z Offset`으로 바닥 높이를 지정하며, Wall Thickness가 0이면 사용할 수 없습니다.
- **Solid**: 닫힌 경로를 위·아래가 막힌 솔리드 블록으로 채웁니다. 같은 높이의 외곽 윤곽과 내부 윤곽은 구멍으로 처리되며, 더 안쪽의 독립 윤곽은 다시 채워지는 중첩 구조도 지원합니다. 윤곽끼리 닿거나 교차하면 생성할 수 없으므로 서로 분리해 주세요.

Section과 Solid는 닫힌 경로가 필요합니다. 열린 경로에서는 패널에 경고가 표시됩니다.

### Materials

Materials 패널에서 다음 네 슬롯을 지정할 수 있습니다.

- **Body**: 벽 몸통과 열린 경로의 양 끝을 막는 면
- **Trim**: 위·아래 및 중간 몰딩 면
- **Top**: 위를 향하는 상단 표면
- **Section**: Section 모드의 내부 바닥

Section 슬롯은 Interior가 Section일 때 표시됩니다.

### UV

**U Scale**과 **V Scale**로 생성된 벽의 UV 스케일을 조절합니다. Section 모드에서는 **Section UV Scale**도 사용할 수 있습니다.

### Advanced

- **Cap Ends**: 열린 경로의 양 끝을 막습니다. 열린 경로가 있을 때 표시됩니다.
- **Miter Limit**: 꺾이는 지점의 코너 보정이 과도하게 뻗는 것을 제한합니다.
- **Merge Distance**: 너무 가까운 샘플 점을 합치는 거리입니다.
- **Resolution**: BEZIER 스플라인을 샘플링하는 방법을 선택합니다. `Custom`은 Segments 값을 사용하고, `Use Curve`는 원본 Curve의 해상도를 사용합니다.
- **Shade Smooth**: 각도 기준의 부드러운 셰이딩을 사용합니다. 켜면 **Smooth Angle**을 지정할 수 있습니다.
- **Add Bevel**: 생성된 벽에 베벨 모디파이어를 추가합니다. 켜면 **Bevel Width**와 **Bevel Segments**를 지정할 수 있습니다.

## 자동 업데이트와 원본 숨기기

- **Auto Update**가 켜져 있으면 설정값 변경과 원본 Curve 편집이 연결된 벽에 자동 반영됩니다. Curve는 Edit Mode에서도 짧은 지연 후 벽이 갱신됩니다. **Show Generated Mesh**를 누르면 남아 있는 대기 업데이트를 반영한 뒤 벽을 보여줍니다.
- **Auto Update**가 꺼져 있으면 **Update Wall**을 눌러 수동으로 갱신합니다.
- **Hide Source**가 켜져 있으면 생성된 벽을 보여줄 때 원본 경로를 숨깁니다. **Edit Source Curve**를 누르면 원본이 다시 표시됩니다.

## 검증 기록

Blender 5.1.1의 테스트 결과와 확인 범위는 [검증 기록](tests/VALIDATION.md)에 정리했습니다.
