# North Star

Status: Current
Owner: Krish Raja
Last verified: 2026-10-18

> By 16 November 2026, every new photo and video Krish takes lands in the library on its own within a week, with nothing to remember.
>
> By 29 March 2027, every old photo album and VHS tape is digitised into it, with nothing lost.

Set by Krish on 18 October 2026 and rewritten by him on 23 October 2026. It is not reached yet. It is what every session in this repository works toward.

## The number

**Share of new photos and videos in the verified library within 7 days of being taken**: 100% by 16 November 2026, on a linear weekly ladder. Checkpoints: 16 Nov 2026: 100%. Gate 2: every old photo album and VHS tape digitised into the library by 29 March 2027, once the inventory is counted.

```yaml north-star-metric
metric: "Share of new photos and videos in the verified library within 7 days of being taken"
unit: %
direction: up
target: 100
deadline: 2026-11-16
ladder_shape: linear
source: "Library ingest log against new captures on Krish's devices and cloud"
status: active
ladder:
  - [2026-10-26, 25.0]
  - [2026-11-02, 50.0]
  - [2026-11-09, 75.0]
  - [2026-11-16, 100.0]
```

Urgency (U1 to U5) is worked out every week from where the number stands against that week's target, by [the harness contract](https://github.com/krishanraja/ai-harness/blob/main/contract/north-star-metric.md). Set by Krish on 23 October 2026.

## How to use it

- Read it before any work, every session.
- Before you start, say which part of it the task moves. If the task moves nothing toward it, say so first and let Krish decide.
- Prefer the work that moves it furthest, and close each session by noting what moved.
- Only Krish changes this file. Record his ruling in the commit body as `Ruling (Krish, YYYY-MM-DD): ...`.
- When it is reached, say so and ask Krish for the next one.
