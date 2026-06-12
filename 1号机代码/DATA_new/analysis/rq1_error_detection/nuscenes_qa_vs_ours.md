# NuScenes-QA (val) vs. Our Suites — Answer/Format Comparison

## Official NuScenes-QA (val)

- total questions: 83337
- distinct sample_tokens (key-frames): 6011
- avg questions per sample: 13.9
- max questions per sample: 32
- distinct answers (answer space size): 30

### Top answers (official)

| answer | count | share |
|---|---:|---:|
| yes | 20519 | 24.6% |
| no | 16924 | 20.3% |
| car | 4515 | 5.4% |
| pedestrian | 4093 | 4.9% |
| moving | 3426 | 4.1% |
| parked | 3072 | 3.7% |
| truck | 2864 | 3.4% |
| stopped | 2165 | 2.6% |
| 3 | 1738 | 2.1% |
| 4 | 1671 | 2.0% |
| 5 | 1668 | 2.0% |
| 2 | 1636 | 2.0% |
| 6 | 1573 | 1.9% |
| 7 | 1545 | 1.9% |
| without rider | 1539 | 1.8% |

### template_type distribution (official)

| template_type | count | share |
|---|---:|---:|
| exist | 24634 | 29.6% |
| object | 17446 | 20.9% |
| count | 16471 | 19.8% |
| comparison | 12809 | 15.4% |
| status | 11977 | 14.4% |

### num_hop distribution (official)

| num_hop | count | share |
|---|---:|---:|
| 1 | 56093 | 67.3% |
| 0 | 27244 | 32.7% |

## Our suites (object-instance)

### advtest_suite
- total questions: 1000
- distinct frames: 11
- distinct answers (answer space): 74
- example answers: car5, car1, car4, bicycle2, ego, bus1, car2, right, True, False
- family/template ids: {'converge': 903, 'viewpoint_transfer': 32, 'distance_chain': 32, 'direction_chain': 33}

### qatest_suite
- total questions: 1000
- distinct frames: 11
- distinct answers (answer space): 72
- example answers: car5, car4, left, car2, False, right, car1, ego, bicycle2, bus1
- family/template ids: {'distance_chain': 224, 'converge': 285, 'viewpoint_transfer': 231, 'direction_chain': 229, 'diverge_compare': 31}

### qaasker_suite
- total questions: 1000
- distinct frames: 11
- distinct answers (answer space): 62
- example answers: False, no, left, yes, right, car4, car2, car5, bus1, car1
- family/template ids: {'direction_chain': 216, 'viewpoint_transfer': 220, 'converge': 322, 'distance_chain': 242}

### random_suite
- total questions: 1000
- distinct frames: 11
- distinct answers (answer space): 70
- example answers: False, car5, right, car4, bicycle2, car1, ego, bus1, True, car2
- family/template ids: {'direction_chain': 237, 'distance_chain': 211, 'viewpoint_transfer': 216, 'converge': 336}
