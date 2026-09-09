# 날카로운 코너 스파이크(Spike) 현상 원인 및 분석

작성일: 2026-06-23

## 1. 문제 현상
- 극단적으로 좁은 각도(예각)를 가진 경로(Curve)에서 Profile Wall Generator를 실행했을 때, 코너 부분이 비정상적으로 길쭉하게 튀어나오는 '스파이크(Spike)' 현상이 발생함.
- UI에서 `Miter Limit` 값을 1.0으로 크게 낮추어도 스파이크 길이에 아무런 변화가 없음.

## 2. 원인 분석

### 2.1. Miter Limit 적용 범위의 한계
- 현재 구현된 `Miter Factor`와 `Miter Limit`은 **프로파일 내부의 돌출 거리(`offset`)** 에만 곱해지는 수식입니다.
- 첨부된 UI 스크린샷 확인 결과, `Offset Scale`이 **0.00**으로 설정되어 있었습니다.
- 수식 상 `offset * offset_scale(0.0) * miter_factor`가 되므로, 스크립트가 자체 계산한 Miter 보정값은 모두 0이 되어 아무런 영향을 주지 못하고 있었습니다. 즉, 스크립트가 생성한 원본(Base) 메시는 두께가 없는 평평한 리본 형태입니다.

### 2.2. Blender Solidify Modifier의 한계
- 화면에 보이는 엄청난 스파이크와 실제 벽 두께(0.5m)는 스크립트가 아닌 **Blender 자체의 Solidify Modifier**가 만들어내고 있습니다.
- Solidify 모디파이어는 `Even Thickness(균일 두께)`를 유지하기 위해 인접한 두 면의 Normal이 만나는 교차점까지 정점을 밀어냅니다. 
- 각도가 극단적으로 좁은 예각일수록 이 교차점은 무한대에 가깝게 멀어지며, Solidify 모디파이어 내부에는 건축적인 형태의 'Miter Limit (잘라내기/Clamp)' 기능이 없기 때문에 그대로 거대한 스파이크를 생성하게 됩니다.

> [!WARNING]
> 결론적으로 현재의 거대한 스파이크는 우리가 작성한 Python 코드가 아니라, Blender의 Solidify 모디파이어 알고리즘이 발생시킨 결과물입니다.

## 3. 해결 방안 (Next Steps)

이 문제를 해결하고 `Miter Limit`을 벽 전체 두께에 완벽하게 적용하기 위해서는 구조적인 개편이 필요합니다.

### 직접 양면 메시 생성 (Solidify 의존성 제거)
- 현재 방식: (1) 얇은 단면 뼈대 생성 -> (2) Solidify Modifier로 두께 부여
- **변경 방식**: (1) Python 코드에서 앞면(Front)과 두께가 반영된 뒷면(Back) 정점을 직접 모두 계산 -> (2) 위, 아래, 양 끝면을 연결하여 닫힌 메시 생성
- **기대 효과**: 
  - `Wall Thickness` 자체에도 스크립트가 계산하는 `Miter Factor`와 `Miter Limit` 수식을 직접 곱할 수 있습니다.
  - 아무리 뾰족한 각도라도 설정된 `Miter Limit` 이상 두께가 튀어나가지 않도록 코너를 수학적으로 잘라낼(Clamp) 수 있습니다.
  - Unity 등으로 내보낼 때 Modifier Apply 과정이 필요 없어 데이터가 안정화됩니다.

---

## 4. 코드 리뷰 (Opus 4.6, 2026-06-23)

### 4.1. 정확한 부분

- **2.1 Miter Limit 적용 범위 분석** — `mesh_builder.py:25`의 수식 `offset * offset_scale * miter_factor`에서 `offset_scale = 0.0`이면 Miter 보정이 전부 무효화된다는 분석은 코드와 일치하며 정확함.
- **2.2 Solidify의 Even Thickness 스파이크** — `mesh_builder.py:118`에서 `use_even_offset = True`를 설정하고 있고, 이 옵션이 예각 코너에서 정점을 극단적으로 밀어내는 원인이라는 분석은 정확함.

### 4.2. 부정확하거나 보완이 필요한 부분

#### (1) "스크립트 코드가 원인이 아니다"는 절반만 맞음

문서에서는 *"우리 코드가 아니라 Solidify가 범인"*이라고 단정하지만, `offset_scale > 0`인 일반적 사용 상황에서는 **스크립트 자체의 miter 계산도 스파이크를 유발**한다.

`path_utils.py:207`의 수식:
```python
miter_factor = (2.0 / (1.0 + dot)) ** 0.5
```
이 수식은 `dot → -1` (극단적 예각)일 때 `miter_factor → ∞`로 발산한다. `mesh_builder.py:23`에서 `min(miter_factors[point_index], props.miter_limit)`으로 클램핑하고 있지만, 기본값 `miter_limit = 3.0`이면 프로파일 offset이 3배까지 뻗어나간다. Solidify만의 문제가 아니라 **스크립트 자체도 스파이크 원인 제공자**임.

#### (2) `offset_scale = 0.0`은 설정 실수가 아닌 의도된 워크플로우일 수 있음

프로파일 돌출 없이 Solidify로만 두께를 부여하는 평평한 벽 생성은 합리적인 사용 패턴이다. 단순히 "설정이 잘못됐다"가 아니라, **이 워크플로우에서 Miter Limit UI가 작동하지 않는 것 자체가 UX 버그**로 봐야 함.

#### (3) 해결 방안이 최고 난이도 안(직접 양면 메시 생성)으로만 제시됨

Solidify 의존성 완전 제거는 대규모 리팩토링이다. 그 전에 즉시 적용 가능한 중간 대안들이 누락되어 있음:

| 대안 | 난이도 | 설명 |
|------|:---:|------|
| `use_even_offset = False`로 변경 | ⭐ | 스파이크 원천 차단. 대신 코너 두께가 불균일해짐 |
| **`thickness_clamp` 속성 활용** (Blender 2.83+) | ⭐ | `modifier.thickness_clamp = 2.0` 등으로 과도한 밀어내기를 제한. 현재 `add_solidify_modifier()`에서 미설정 |
| 예각 코너 자동 베벨/분할 삽입 | ⭐⭐⭐ | 코너 각도가 threshold 이하면 경로 포인트를 2개로 분할 |
| 직접 양면 메시 생성 (문서 제안) | ⭐⭐⭐⭐⭐ | 완전한 제어 가능, 대규모 리팩토링 필요 |

> [!IMPORTANT]
> 특히 `thickness_clamp`는 Blender Solidify 모디파이어에 이미 존재하는 속성이며, `mesh_builder.py:add_solidify_modifier()`에 한 줄 추가(`modifier.thickness_clamp = props.miter_limit` 등)만으로 상당 부분 해결 가능하다. 전면 리팩토링 전에 먼저 시도할 것을 권장.

### 4.3. 최종 평가

| 항목 | 평가 |
|------|------|
| 문제 현상 기술 | ✅ 정확 |
| Offset Scale = 0 → Miter 무효화 분석 | ✅ 정확 |
| Solidify Even Thickness 한계 분석 | ✅ 정확 |
| "코드 무죄, Solidify만 범인" 결론 | ⚠️ 절반만 맞음 (offset_scale > 0 케이스 누락) |
| 대안 제시 | ⚠️ 최고 난이도 안만 제시, 즉시 적용 가능한 `thickness_clamp` 등 누락 |
| **전반적 품질** | **70점** — 분석 자체는 괜찮으나 코드 리딩이 표면적이고 해결 방안이 편향됨 |

### 4.4. `thickness_clamp` 적용 결과 및 최종 리팩토링 (2026-06-23 업데이트)

위에서 지적한 대로 `thickness_clamp` 속성을 활용해 스파이크를 제한하려 시도했으나, Solidify 모디파이어의 한계가 추가로 발견되었다.

- **`thickness_clamp`의 부작용**: 이 기능은 가장 짧은 엣지(Edge) 길이에 비례하여 두께를 제한하기 때문에, 원본 커브에 짧은 세그먼트가 포함되어 있으면 벽 전체 두께가 얇게 고정되는 치명적인 문제가 발생했다.
- **결론**: 따라서 "직접 양면 메시 생성" (Solidify 모디파이어 제거) 방식이 단순한 리팩토링이 아니라, Blender의 구조적 한계를 우회하기 위한 **유일한 근본적 해결책**으로 확인되었다.

현재 `mesh_builder.py`는 Solidify 모디파이어 호출을 제거하고, Python 단에서 직접 앞면(Front)과 뒷면(Back) 정점을 모두 계산하여 닫힌 공간을 만드는 방식으로 전면 개편되었다. 이를 통해 `offset_scale`과 `wall_thickness` 모두에 `miter_limit`이 일관되게 적용되어 스파이크 현상이 완벽히 차단되었다.
