# UX1.4 Turn 1.1 — Elastic Radial Geometry Polish

Продолжаем **UX1.4 Turn 1**. Visual acceptance пока не пройден.

Сделай только **Turn 1.1 — Elastic Radial Geometry Polish**.

Turn 2, GIF, connectors, Soul HUD и Money HUD пока **НЕ начинать**.

## 1. Основные проблемы

Сейчас:

1. Workspace всё ещё недостаточно читается как кольцо вокруг Character Core.
2. Inventory находится слишком близко к Core.
3. Apotheosis имеет плохую inner content area — текст сжат внешней геометрией.
4. Будущие реальные данные будут менять размеры блоков, поэтому фиксированные абсолютные координаты недостаточны.

## 2. Elastic radial composition

Character Core остаётся центром.

Семантические углы nodes постоянны:

```text
                         Party

            Map                         Lifestyle

       Tiamana             Core              Quests

            Notes                      Apotheosis

                        Inventory
```

Но расстояние от Core **НЕ должно быть жёстко заданным навсегда**.

Нужно реализовать **elastic radial layout**:

```text
stable node angles
+
adaptive horizontal/vertical radius
```

Если один или несколько reflection nodes становятся больше, radial field должен автоматически немного расширяться, сохраняя Character Core в центре, общую radial hierarchy, стабильный порядок nodes, safe gaps и отсутствие overlap.

Это особенно важно для будущих Inventory, Party, Quests и Lifestyle data.

## 3. Размеры определяются реальным content

Не считать, что Reflection Nodes всегда имеют нынешнюю placeholder-высоту.

Layout должен поддерживать:

```text
node content changes
↓
node dimensions change
↓
radial clearance recalculates
↓
ring expands/contracts
```

Не делать постоянный RAF layout engine.

Предпочтительно:

- initial layout calculation;
- `ResizeObserver` для radial scene / relevant nodes;
- viewport `resize`;
- пересчёт только когда geometry реально изменилась.

Если CSS-only решение надёжно выполняет те же требования — можно использовать его.

## 4. Radial geometry

Не использовать случайный scatter.

Node angles остаются стабильными:

```text
Party        top
Map          upper-left
Lifestyle    upper-right
Tiamana      left
Quests       right
Notes        lower-left
Apotheosis   lower-right
Inventory    bottom
Core         center
```

При росте required radius все outer nodes немного отходят от Core.

Horizontal и vertical radius могут изменяться независимо, то есть кольцо может быть эллиптическим.

## 5. Central safe zone

Вокруг Character Core всегда оставлять свободную центральную область.

Ни один node не должен вторгаться в неё.

Это пространство требуется будущему Turn 2:

- Character aura;
- radial connectors;
- Focus Field depth.

Центральный clearance должен учитываться radial layout engine.

## 6. Inventory placement

Inventory — bottom radial anchor.

Сделать его:

- широким горизонтальным shard;
- bottom-center;
- более материальным, чем остальные;
- не footer;
- не маленькой квадратной карточкой.

Внутренняя композиция:

```text
ПРИ СЕБЕ
Инвентарь            Вещи ещё не проступили.
```

## 7. Future Inventory growth contract

Уже сейчас layout должен быть готов к тому, что после I1 Inventory preview станет примерно:

```text
ПРИ СЕБЕ
Инвентарь

item
item
item
item
```

UX1.4 не реализует Inventory backend и не создаёт fake items.

Только подготовить geometry/CSS contract.

Main Workspace Inventory никогда не должен показывать unlimited list.

Предусмотреть bounded preview area примерно максимум на **4 item rows**.

Если в будущем предметов больше, I1 будет показывать ограниченный preview и переход к полному Inventory.

Не делать nested scrollbar внутри Inventory shard.

## 8. Generic bounded-preview principle

Radial layout должен поддерживать variable content, но Character Workspace не должен бесконечно разрастаться от данных.

В будущем:

```text
Notes       bounded preview
Quests      bounded preview
Inventory   bounded preview
Party       bounded preview
Lifestyle   bounded preview
```

Полный content открывается в dedicated section.

## 9. Apotheosis safe zone

Исправить текущий сжатый текст.

Каждый Dark Glass shard должен иметь:

```text
outer decorative silhouette
+
inner readable safe-zone
```

Внешний `clip-path` не должен определять usable text width.

Для Apotheosis:

- нормальная ширина title;
- description свободно помещается;
- icon получает свою область;
- padding учитывает самые глубокие срезы silhouette.

Проверить тот же принцип на остальных nodes.

Decorative geometry никогда не должна ухудшать читаемость.

## 10. Pair balance

Визуальные пары:

```text
Map ↔ Lifestyle
Tiamana ↔ Quests
Notes ↔ Apotheosis
```

должны иметь сопоставимую visual mass.

Они не обязаны иметь одинаковые размеры.

Если одна сторона имеет более высокий content, elastic ring адаптируется, не разрушая баланс.

Party остаётся верхним широким anchor.

Inventory — нижним широким anchor.

## 11. Focus Field

Существующую UX1.3 Focus state machine **НЕ переписывать**.

После radial repositioning Focus Field продолжает работать с фактической geometry nodes.

При изменении layout обязательно invalidировать cached node geometry, если существующий Focus engine её кеширует.

Не допустить возвращения stuck focus/glow bug.

## 12. Mobile

На `390×844` radial engine не используется.

Сохраняется нормальная вертикальная Character composition.

Variable node heights должны естественно расширять document flow.

No horizontal overflow.

## 13. Проверки

Не делать screenshots — пользователь проверит внешний вид сам.

Не запускать full suite.

Достаточно:

- `manage.py check`;
- targeted presentation tests только если template/JS contract изменён;
- `git diff --check`;
- quick browser sanity без сохранения screenshot, если нужен для проверки overlap/layout.

Обновить:

```text
docs/UX1_4_PROGRESS.md
```

Зафиксировать:

- выбранный elastic layout approach;
- как пересчитывается radius;
- как обрабатывается node resize;
- Inventory preview contract;
- Apotheosis safe-zone fix.

После этого **STOP**.

Turn 2 не начинать.
