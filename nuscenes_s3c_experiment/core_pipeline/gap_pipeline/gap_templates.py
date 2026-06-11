"""
Gap Pipeline — Template Library
75 template IDs × 4 variants = 300 question templates.

Template variable keys (all strings, may be empty-string if unavailable):
    src_id, src_type, src_status
    tgt_id, tgt_type, tgt_status
    dir4, dir8, dist_level
    anc_id, anc_type            (L2A context, may be empty)
    beyond_id, beyond_type      (L2B context, may be empty)

TEMPLATE_META fields:
    difficulty   : "edge" | "L2"
    category     : "direction" | "distance" | "existence" | "status" |
                   "type" | "comparison" | "L2A" | "L2B"
    answer_type  : "open" | "yes_no"
    answer_source: string token describing how to derive the answer (see resolve_answer)
    requires     : list of tvars keys that must be non-empty for the template to apply
"""
import random
from typing import Dict, List

# ---------------------------------------------------------------------------
# Template strings  (75 IDs × 4 variants each)
# ---------------------------------------------------------------------------

TEMPLATE_STRINGS: Dict[str, List[str]] = {

    # -----------------------------------------------------------------------
    # D01-D15  Direction (15 templates)
    # -----------------------------------------------------------------------
    "D01": [
        "What direction is {tgt_type} {tgt_id} from {src_type} {src_id}?",
        "In which direction is {tgt_type} {tgt_id} relative to {src_type} {src_id}?",
        "Where is {tgt_type} {tgt_id} with respect to {src_type} {src_id}?",
        "Which way is {tgt_type} {tgt_id} from {src_type} {src_id}?",
    ],
    "D02": [
        "In what direction does {src_type} {src_id} see {tgt_type} {tgt_id}?",
        "From {src_type} {src_id}'s perspective, where is {tgt_type} {tgt_id}?",
        "What is the bearing from {src_type} {src_id} to {tgt_type} {tgt_id}?",
        "From {src_type} {src_id}, in what direction can {tgt_type} {tgt_id} be found?",
    ],
    "D03": [
        "Is {tgt_type} {tgt_id} to the {dir8} of {src_type} {src_id}?",
        "Can {tgt_type} {tgt_id} be found to the {dir8} of {src_type} {src_id}?",
        "Does {tgt_type} {tgt_id} lie in the {dir8} direction from {src_type} {src_id}?",
        "Is the direction from {src_type} {src_id} to {tgt_type} {tgt_id} {dir8}?",
    ],
    "D04": [
        "What is the 8-direction label from {src_type} {src_id} to {tgt_type} {tgt_id}?",
        "Using 8-direction notation, where is {tgt_type} {tgt_id} from {src_type} {src_id}?",
        "Which of the eight directions describes {tgt_type} {tgt_id} relative to {src_type} {src_id}?",
        "Give the 8-direction bearing from {src_type} {src_id} to {tgt_type} {tgt_id}.",
    ],
    "D05": [
        "What cardinal side (front/left/right/back) of {src_type} {src_id} is {tgt_type} {tgt_id} on?",
        "On which side of {src_type} {src_id} does {tgt_type} {tgt_id} sit?",
        "To which 4-direction sector of {src_type} {src_id} does {tgt_type} {tgt_id} belong?",
        "In which major direction sector from {src_type} {src_id} is {tgt_type} {tgt_id}?",
    ],
    "D06": [
        "Is there a {tgt_type} to the {dir8} of {src_type} {src_id}?",
        "Can a {tgt_type} be found to the {dir8} of {src_type} {src_id}?",
        "Does a {tgt_type} exist in the {dir8} direction from {src_type} {src_id}?",
        "Is a {tgt_type} present to the {dir8} of {src_type} {src_id}?",
    ],
    "D07": [
        "What object is to the {dir8} of {src_type} {src_id}?",
        "What can be found to the {dir8} of {src_type} {src_id}?",
        "What is located in the {dir8} direction from {src_type} {src_id}?",
        "Which object lies to the {dir8} of {src_type} {src_id}?",
    ],
    "D08": [
        "Is {tgt_type} {tgt_id} in front of or behind {src_type} {src_id}?",
        "Along the front-back axis, where is {tgt_type} {tgt_id} relative to {src_type} {src_id}?",
        "Is {tgt_type} {tgt_id} ahead of or behind {src_type} {src_id}?",
        "With respect to {src_type} {src_id}, is {tgt_type} {tgt_id} in front or behind?",
    ],
    "D09": [
        "From which direction is {tgt_type} {tgt_id} approaching {src_type} {src_id}?",
        "In which direction does {tgt_type} {tgt_id} approach {src_type} {src_id}?",
        "What direction marks {tgt_type} {tgt_id} relative to {src_type} {src_id}?",
        "Which direction separates {src_type} {src_id} and {tgt_type} {tgt_id}?",
    ],
    "D10": [
        "What object can be found in the {dir4} sector of {src_type} {src_id}?",
        "Which object is in the {dir4} of {src_type} {src_id}?",
        "Name the object located in the {dir4} direction from {src_type} {src_id}.",
        "In the {dir4} sector of {src_type} {src_id}, what object is present?",
    ],
    "D11": [
        "What type of object is at the {dir8} of {src_type} {src_id}?",
        "What kind of object lies in the {dir8} direction from {src_type} {src_id}?",
        "Identify the object type found to the {dir8} of {src_type} {src_id}.",
        "What category of object occupies the {dir8} position of {src_type} {src_id}?",
    ],
    "D12": [
        "To which cardinal direction from {src_type} {src_id} is {tgt_type} {tgt_id}?",
        "What major direction (front/left/right/back) points from {src_type} {src_id} to {tgt_type} {tgt_id}?",
        "In terms of the four cardinal directions, where is {tgt_type} {tgt_id} from {src_type} {src_id}?",
        "Give the 4-direction bearing from {src_type} {src_id} to {tgt_type} {tgt_id}.",
    ],
    "D13": [
        "What is located to the {dir8} of {src_type} {src_id}?",
        "Name the object to the {dir8} of {src_type} {src_id}.",
        "Which object can be found at the {dir8} position of {src_type} {src_id}?",
        "What sits to the {dir8} of {src_type} {src_id}?",
    ],
    "D14": [
        "Is {tgt_type} {tgt_id} at the {dir8} of {src_type} {src_id}?",
        "Does {tgt_type} {tgt_id} occupy the {dir8} position of {src_type} {src_id}?",
        "Can {tgt_type} {tgt_id} be placed at the {dir8} of {src_type} {src_id}?",
        "Is the {dir8} of {src_type} {src_id} occupied by {tgt_type} {tgt_id}?",
    ],
    "D15": [
        "Which of the eight directions describes {tgt_type} {tgt_id} seen from {src_type} {src_id}?",
        "Using 8-point compass notation, how would you describe the position of {tgt_type} {tgt_id} from {src_type} {src_id}?",
        "What is the 8-compass direction from {src_type} {src_id} toward {tgt_type} {tgt_id}?",
        "Select the 8-direction sector that contains {tgt_type} {tgt_id} as viewed from {src_type} {src_id}.",
    ],

    # -----------------------------------------------------------------------
    # T01-T10  Distance (10 templates)
    # -----------------------------------------------------------------------
    "T01": [
        "How far is {tgt_type} {tgt_id} from {src_type} {src_id}?",
        "What is the distance level between {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "How would you classify the distance from {src_type} {src_id} to {tgt_type} {tgt_id}?",
        "Describe the distance between {src_type} {src_id} and {tgt_type} {tgt_id}.",
    ],
    "T02": [
        "What is the distance category between {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "How is the distance from {src_type} {src_id} to {tgt_type} {tgt_id} classified?",
        "Which distance bucket covers the gap between {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "What distance label applies to the separation of {src_type} {src_id} and {tgt_type} {tgt_id}?",
    ],
    "T03": [
        "Is {tgt_type} {tgt_id} very close to {src_type} {src_id}?",
        "Would you describe {tgt_type} {tgt_id} as very close to {src_type} {src_id}?",
        "Is the distance between {src_type} {src_id} and {tgt_type} {tgt_id} very close?",
        "Does {tgt_type} {tgt_id} fall in the very-close range of {src_type} {src_id}?",
    ],
    "T04": [
        "Is {tgt_type} {tgt_id} far from {src_type} {src_id}?",
        "Would you describe {tgt_type} {tgt_id} as far from {src_type} {src_id}?",
        "Is the separation between {src_type} {src_id} and {tgt_type} {tgt_id} categorised as far?",
        "Does {tgt_type} {tgt_id} lie in the far-range zone of {src_type} {src_id}?",
    ],
    "T05": [
        "How would you describe the distance between {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "What proximity label applies between {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "Characterise the distance separating {src_type} {src_id} and {tgt_type} {tgt_id}.",
        "In distance terms, how separated are {src_type} {src_id} and {tgt_type} {tgt_id}?",
    ],
    "T06": [
        "Is {tgt_type} {tgt_id} close to {src_type} {src_id}?",
        "Would you say {tgt_type} {tgt_id} is close to {src_type} {src_id}?",
        "Is the distance between {src_type} {src_id} and {tgt_type} {tgt_id} close?",
        "Does {tgt_type} {tgt_id} fall in the close-range zone of {src_type} {src_id}?",
    ],
    "T07": [
        "What proximity level describes {tgt_type} {tgt_id} relative to {src_type} {src_id}?",
        "State the proximity category from {src_type} {src_id} to {tgt_type} {tgt_id}.",
        "What is the proximity rating between {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "Which proximity tier applies to {tgt_type} {tgt_id} as seen from {src_type} {src_id}?",
    ],
    "T08": [
        "Is the distance between {src_type} {src_id} and {tgt_type} {tgt_id} in the medium range?",
        "Does a medium-range distance separate {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "Is {tgt_type} {tgt_id} at medium distance from {src_type} {src_id}?",
        "Would medium describe the distance between {src_type} {src_id} and {tgt_type} {tgt_id}?",
    ],
    "T09": [
        "How close is {tgt_type} {tgt_id} to {src_type} {src_id}?",
        "What is the closeness level of {tgt_type} {tgt_id} to {src_type} {src_id}?",
        "Describe how close {tgt_type} {tgt_id} is to {src_type} {src_id}.",
        "In distance terms, how near is {tgt_type} {tgt_id} to {src_type} {src_id}?",
    ],
    "T10": [
        "Is {tgt_type} {tgt_id} within close range of {src_type} {src_id}?",
        "Does {tgt_type} {tgt_id} lie within close distance of {src_type} {src_id}?",
        "Is {tgt_type} {tgt_id} in the close-or-nearer zone of {src_type} {src_id}?",
        "Can {tgt_type} {tgt_id} be considered within close range of {src_type} {src_id}?",
    ],

    # -----------------------------------------------------------------------
    # E01-E12  Existence (12 templates)
    # -----------------------------------------------------------------------
    "E01": [
        "Is there a {tgt_type} to the {dir8} of {src_type} {src_id}?",
        "Can a {tgt_type} be seen to the {dir8} of {src_type} {src_id}?",
        "Does a {tgt_type} appear to the {dir8} of {src_type} {src_id}?",
        "Is a {tgt_type} present to the {dir8} of {src_type} {src_id}?",
    ],
    "E02": [
        "Does a {tgt_type} exist at the {dir8} of {src_type} {src_id}?",
        "Is there any {tgt_type} existing at the {dir8} position of {src_type} {src_id}?",
        "Can the presence of a {tgt_type} be confirmed at the {dir8} of {src_type} {src_id}?",
        "Is a {tgt_type} found at the {dir8} location of {src_type} {src_id}?",
    ],
    "E03": [
        "Can you see a {tgt_type} in the {dir4} direction of {src_type} {src_id}?",
        "Is a {tgt_type} visible in the {dir4} sector of {src_type} {src_id}?",
        "Does the {dir4} sector of {src_type} {src_id} contain a {tgt_type}?",
        "Is there a {tgt_type} in the {dir4} area from {src_type} {src_id}?",
    ],
    "E04": [
        "Is {tgt_type} {tgt_id} present in the scene?",
        "Does {tgt_type} {tgt_id} appear in this frame?",
        "Can {tgt_type} {tgt_id} be observed in the current scene?",
        "Is {tgt_type} {tgt_id} part of the current scene?",
    ],
    "E05": [
        "Does {tgt_type} {tgt_id} exist in this frame?",
        "Is {tgt_type} {tgt_id} detected in this scene?",
        "Is there a record of {tgt_type} {tgt_id} in the current frame?",
        "Does this scene include {tgt_type} {tgt_id}?",
    ],
    "E06": [
        "Is there any {tgt_type} near {src_type} {src_id}?",
        "Can a {tgt_type} be found nearby {src_type} {src_id}?",
        "Is a {tgt_type} present in the vicinity of {src_type} {src_id}?",
        "Does {src_type} {src_id} have a nearby {tgt_type}?",
    ],
    "E07": [
        "Are there objects to the {dir8} of {src_type} {src_id}?",
        "Is the {dir8} side of {src_type} {src_id} occupied?",
        "Can any object be found to the {dir8} of {src_type} {src_id}?",
        "Does the {dir8} of {src_type} {src_id} contain any object?",
    ],
    "E08": [
        "Is {src_type} {src_id} present in the scene?",
        "Does {src_type} {src_id} appear in this frame?",
        "Is {src_type} {src_id} detected in the current scene?",
        "Is there a {src_type} identified as {src_id} in this scene?",
    ],
    "E09": [
        "Is there a {tgt_type} at {dist_level} range from {src_type} {src_id}?",
        "Does a {tgt_type} exist at {dist_level} distance from {src_type} {src_id}?",
        "Can a {tgt_type} be found at {dist_level} range from {src_type} {src_id}?",
        "Is a {tgt_type} present {dist_level} away from {src_type} {src_id}?",
    ],
    "E10": [
        "Does the scene contain a {tgt_type} to the {dir8} of {src_type} {src_id}?",
        "Is a {tgt_type} to the {dir8} of {src_type} {src_id} part of the scene?",
        "Does this scene include a {tgt_type} to the {dir8} of {src_type} {src_id}?",
        "Is a {tgt_type} at the {dir8} position of {src_type} {src_id} observable?",
    ],
    "E11": [
        "Are there any objects at {dist_level} distance from {src_type} {src_id}?",
        "Does the {dist_level}-distance zone of {src_type} {src_id} contain any objects?",
        "Can any object be found at {dist_level} range from {src_type} {src_id}?",
        "Is the {dist_level} range of {src_type} {src_id} populated with objects?",
    ],
    "E12": [
        "Is {tgt_type} {tgt_id} one of the objects in this frame?",
        "Is {tgt_type} {tgt_id} included among the objects in this scene?",
        "Does this frame contain {tgt_type} {tgt_id}?",
        "Is {tgt_type} {tgt_id} visible in the current frame?",
    ],

    # -----------------------------------------------------------------------
    # S01-S12  Status (12 templates)
    # -----------------------------------------------------------------------
    "S01": [
        "What is the status of {tgt_type} {tgt_id}?",
        "What motion state is {tgt_type} {tgt_id} in?",
        "Describe the current status of {tgt_type} {tgt_id}.",
        "What is {tgt_type} {tgt_id} doing right now?",
    ],
    "S02": [
        "Is {tgt_type} {tgt_id} moving?",
        "Is {tgt_type} {tgt_id} in motion?",
        "Does {tgt_type} {tgt_id} appear to be moving?",
        "Can {tgt_type} {tgt_id} be observed moving?",
    ],
    "S03": [
        "What is the motion state of {tgt_type} {tgt_id}?",
        "How would you describe the motion of {tgt_type} {tgt_id}?",
        "State the movement status of {tgt_type} {tgt_id}.",
        "What movement category applies to {tgt_type} {tgt_id}?",
    ],
    "S04": [
        "Is {tgt_type} {tgt_id} stationary?",
        "Has {tgt_type} {tgt_id} stopped?",
        "Is {tgt_type} {tgt_id} not moving?",
        "Does {tgt_type} {tgt_id} appear stationary?",
    ],
    "S05": [
        "What is the current status of {src_type} {src_id}?",
        "What motion state is {src_type} {src_id} in?",
        "Describe the current status of {src_type} {src_id}.",
        "What is {src_type} {src_id} doing right now?",
    ],
    "S06": [
        "Is {src_type} {src_id} moving?",
        "Is {src_type} {src_id} in motion?",
        "Does {src_type} {src_id} appear to be moving?",
        "Can {src_type} {src_id} be observed moving?",
    ],
    "S07": [
        "Is the {tgt_type} to the {dir8} of {src_type} {src_id} moving?",
        "Does the {tgt_type} at the {dir8} of {src_type} {src_id} appear to be moving?",
        "Is the {tgt_type} in the {dir8} direction from {src_type} {src_id} in motion?",
        "Can the {tgt_type} to the {dir8} of {src_type} {src_id} be seen moving?",
    ],
    "S08": [
        "What is the status of the {tgt_type} at the {dir8} of {src_type} {src_id}?",
        "What is the motion state of the {tgt_type} to the {dir8} of {src_type} {src_id}?",
        "Describe the status of the {tgt_type} located at the {dir8} of {src_type} {src_id}.",
        "What is the {tgt_type} at the {dir8} of {src_type} {src_id} doing?",
    ],
    "S09": [
        "Is {tgt_type} {tgt_id} stopped?",
        "Has {tgt_type} {tgt_id} come to a stop?",
        "Is {tgt_type} {tgt_id} in a stopped state?",
        "Would you classify {tgt_type} {tgt_id} as stopped?",
    ],
    "S10": [
        "Is the {tgt_type} to the {dir8} of {src_type} {src_id} stationary?",
        "Does the {tgt_type} at the {dir8} of {src_type} {src_id} appear stationary?",
        "Has the {tgt_type} in the {dir8} direction of {src_type} {src_id} stopped?",
        "Is the {tgt_type} at the {dir8} position of {src_type} {src_id} not moving?",
    ],
    "S11": [
        "How would you describe the movement of {tgt_type} {tgt_id}?",
        "What movement label applies to {tgt_type} {tgt_id}?",
        "Describe the motion behaviour of {tgt_type} {tgt_id}.",
        "What is the motion classification of {tgt_type} {tgt_id}?",
    ],
    "S12": [
        "Is {src_type} {src_id} currently in motion?",
        "Is {src_type} {src_id} moving at the moment?",
        "Does {src_type} {src_id} appear to be moving right now?",
        "Can {src_type} {src_id} be considered in motion?",
    ],

    # -----------------------------------------------------------------------
    # O01-O08  Type / Object (8 templates)
    # -----------------------------------------------------------------------
    "O01": [
        "What type of object is {tgt_id}?",
        "What kind of object is {tgt_id}?",
        "What category does {tgt_id} belong to?",
        "Identify the type of object labelled {tgt_id}.",
    ],
    "O02": [
        "What kind of object is to the {dir8} of {src_type} {src_id}?",
        "What type of object can be found to the {dir8} of {src_type} {src_id}?",
        "Identify the object type at the {dir8} of {src_type} {src_id}.",
        "What kind of thing is located to the {dir8} of {src_type} {src_id}?",
    ],
    "O03": [
        "Identify the object at {dist_level} range to the {dir8} of {src_type} {src_id}.",
        "What object is at {dist_level} distance in the {dir8} of {src_type} {src_id}?",
        "Name the object that is {dist_level} away and to the {dir8} of {src_type} {src_id}.",
        "What is the object found {dist_level} away to the {dir8} of {src_type} {src_id}?",
    ],
    "O04": [
        "What is the object closest to {src_type} {src_id} to the {dir8}?",
        "Which object is nearest to {src_type} {src_id} in the {dir8} direction?",
        "What object in the {dir8} direction is most proximate to {src_type} {src_id}?",
        "Name the object that is closest to {src_type} {src_id} on the {dir8} side.",
    ],
    "O05": [
        "Is {tgt_id} a vehicle?",
        "Would {tgt_id} be classified as a vehicle?",
        "Does {tgt_id} belong to the vehicle category?",
        "Is {tgt_id} a type of vehicle?",
    ],
    "O06": [
        "Is {tgt_id} a pedestrian?",
        "Would {tgt_id} be classified as a pedestrian?",
        "Does {tgt_id} belong to the pedestrian category?",
        "Is {tgt_id} a type of pedestrian?",
    ],
    "O07": [
        "What category does {tgt_id} belong to?",
        "Under which object category is {tgt_id} classified?",
        "To what type category does {tgt_id} belong?",
        "How is {tgt_id} categorised in the scene graph?",
    ],
    "O08": [
        "What kind of object is {tgt_id}?",
        "Describe the type of {tgt_id}.",
        "What is {tgt_id} classified as?",
        "What object type best describes {tgt_id}?",
    ],

    # -----------------------------------------------------------------------
    # C01-C08  Comparison (8 templates)
    # -----------------------------------------------------------------------
    "C01": [
        "Are {src_type} {src_id} and {tgt_type} {tgt_id} both moving?",
        "Is it true that both {src_type} {src_id} and {tgt_type} {tgt_id} are moving?",
        "Do {src_type} {src_id} and {tgt_type} {tgt_id} share a moving status?",
        "Are both {src_type} {src_id} and {tgt_type} {tgt_id} in motion?",
    ],
    "C02": [
        "Are {src_type} {src_id} and {tgt_type} {tgt_id} both stationary?",
        "Is it true that both {src_type} {src_id} and {tgt_type} {tgt_id} are stationary?",
        "Do {src_type} {src_id} and {tgt_type} {tgt_id} share a stationary status?",
        "Are both {src_type} {src_id} and {tgt_type} {tgt_id} not moving?",
    ],
    "C03": [
        "Do {src_type} {src_id} and {tgt_type} {tgt_id} have the same motion status?",
        "Is the motion status of {src_type} {src_id} the same as that of {tgt_type} {tgt_id}?",
        "Are {src_type} {src_id} and {tgt_type} {tgt_id} in the same motion state?",
        "Do {src_type} {src_id} and {tgt_type} {tgt_id} share the same movement state?",
    ],
    "C04": [
        "Is {src_type} {src_id} moving while {tgt_type} {tgt_id} is stationary?",
        "Is {src_type} {src_id} in motion while {tgt_type} {tgt_id} is stopped?",
        "Does {src_type} {src_id} move as {tgt_type} {tgt_id} remains stationary?",
        "While {tgt_type} {tgt_id} is stationary, is {src_type} {src_id} moving?",
    ],
    "C05": [
        "Is {tgt_type} {tgt_id} moving while {src_type} {src_id} is stationary?",
        "Is {tgt_type} {tgt_id} in motion while {src_type} {src_id} is stopped?",
        "Does {tgt_type} {tgt_id} move as {src_type} {src_id} remains stationary?",
        "While {src_type} {src_id} is stationary, is {tgt_type} {tgt_id} moving?",
    ],
    "C06": [
        "Is {tgt_type} {tgt_id} closer or farther than {dist_level} from {src_type} {src_id}?",
        "Relative to the {dist_level} threshold, where does {tgt_type} {tgt_id} stand from {src_type} {src_id}?",
        "Is {tgt_type} {tgt_id} within {dist_level} range of {src_type} {src_id}?",
        "Would {tgt_type} {tgt_id} be described as within {dist_level} distance of {src_type} {src_id}?",
    ],
    "C07": [
        "Is the distance between {src_type} {src_id} and {tgt_type} {tgt_id} categorised as {dist_level}?",
        "Does a {dist_level} distance separate {src_type} {src_id} and {tgt_type} {tgt_id}?",
        "Is {tgt_type} {tgt_id} at {dist_level} distance from {src_type} {src_id}?",
        "Is the {src_type} {src_id} to {tgt_type} {tgt_id} gap at the {dist_level} level?",
    ],
    "C08": [
        "Does {tgt_type} {tgt_id} have the same distance level as its direction label from {src_type} {src_id}?",
        "What distance and direction characterise {tgt_type} {tgt_id} relative to {src_type} {src_id}?",
        "Summarise the spatial relationship between {src_type} {src_id} and {tgt_type} {tgt_id}.",
        "How would you describe the combined distance and direction from {src_type} {src_id} to {tgt_type} {tgt_id}?",
    ],

    # -----------------------------------------------------------------------
    # LA01-LA05  L2A  (ancestor → src → tgt)
    # -----------------------------------------------------------------------
    "LA01": [
        "What is to the {dir8} of {src_type} {src_id}, which is itself near {anc_type} {anc_id}?",
        "Given that {src_type} {src_id} is close to {anc_type} {anc_id}, what lies to the {dir8} of {src_type} {src_id}?",
        "If {anc_type} {anc_id} is beside {src_type} {src_id}, what is to the {dir8} of {src_type} {src_id}?",
        "Knowing {anc_type} {anc_id} is near {src_type} {src_id}, identify the object to the {dir8} of {src_type} {src_id}.",
    ],
    "LA02": [
        "Is {tgt_type} {tgt_id} connected to {anc_type} {anc_id} through {src_type} {src_id}?",
        "Does a path exist from {anc_type} {anc_id} to {tgt_type} {tgt_id} via {src_type} {src_id}?",
        "Can {tgt_type} {tgt_id} be reached from {anc_type} {anc_id} by going through {src_type} {src_id}?",
        "Is there a two-hop link from {anc_type} {anc_id} through {src_type} {src_id} to {tgt_type} {tgt_id}?",
    ],
    "LA03": [
        "What object is between {anc_type} {anc_id} and {tgt_type} {tgt_id} in the spatial chain?",
        "Which object acts as intermediary between {anc_type} {anc_id} and {tgt_type} {tgt_id}?",
        "Name the object that bridges {anc_type} {anc_id} and {tgt_type} {tgt_id} in the scene.",
        "What lies between {anc_type} {anc_id} and {tgt_type} {tgt_id} spatially?",
    ],
    "LA04": [
        "If {anc_type} {anc_id} is adjacent to {src_type} {src_id}, what is to the {dir8} of {src_type} {src_id}?",
        "Given the proximity of {anc_type} {anc_id} to {src_type} {src_id}, what object is to the {dir8} of {src_type} {src_id}?",
        "With {anc_type} {anc_id} next to {src_type} {src_id}, what appears to the {dir8} of {src_type} {src_id}?",
        "Since {anc_type} {anc_id} is near {src_type} {src_id}, what is the {dir8} neighbour of {src_type} {src_id}?",
    ],
    "LA05": [
        "What is the status of {tgt_type} {tgt_id}, the object to the {dir8} of {src_type} {src_id} near {anc_type} {anc_id}?",
        "Given {anc_type} {anc_id} is near {src_type} {src_id}, what is the status of the {tgt_type} to the {dir8}?",
        "What motion state is {tgt_type} {tgt_id} in, the object to the {dir8} of {src_type} {src_id} (itself near {anc_type} {anc_id})?",
        "Describe the status of {tgt_type} {tgt_id}, which is to the {dir8} of {src_type} {src_id} near {anc_type} {anc_id}.",
    ],

    # -----------------------------------------------------------------------
    # LB01-LB05  L2B  (src → tgt → beyond)
    # -----------------------------------------------------------------------
    "LB01": [
        "Is there another object beyond {tgt_type} {tgt_id} continuing in the direction from {src_type} {src_id}?",
        "Does any object lie beyond {tgt_type} {tgt_id} along the path from {src_type} {src_id}?",
        "Past {tgt_type} {tgt_id}, is there a further object on the {dir8} side of {src_type} {src_id}?",
        "Is a second object present beyond {tgt_type} {tgt_id} in the {dir8} direction from {src_type} {src_id}?",
    ],
    "LB02": [
        "What is {beyond_type} {beyond_id}, the object past {tgt_type} {tgt_id} from {src_type} {src_id}?",
        "Describe {beyond_type} {beyond_id}, which lies beyond {tgt_type} {tgt_id} as seen from {src_type} {src_id}.",
        "What type is {beyond_id}, the object further along from {tgt_type} {tgt_id}?",
        "What kind of object is {beyond_id}, found beyond {tgt_type} {tgt_id} from {src_type} {src_id}?",
    ],
    "LB03": [
        "If {tgt_type} {tgt_id} is to the {dir8} of {src_type} {src_id}, what object is further along in that direction?",
        "Beyond {tgt_type} {tgt_id} in the {dir8} direction from {src_type} {src_id}, what do you find?",
        "Continuing past {tgt_type} {tgt_id} from {src_type} {src_id}, what object appears next?",
        "What object comes after {tgt_type} {tgt_id} along the {dir8} path from {src_type} {src_id}?",
    ],
    "LB04": [
        "What type of object is found beyond {tgt_type} {tgt_id} in the {dir8} direction from {src_type} {src_id}?",
        "What kind of object lies beyond {tgt_type} {tgt_id} continuing from {src_type} {src_id} in the {dir8}?",
        "Identify the type of the object beyond {tgt_type} {tgt_id} along the {dir8} axis from {src_type} {src_id}.",
        "What object category is present beyond {tgt_type} {tgt_id} on the {dir8} path from {src_type} {src_id}?",
    ],
    "LB05": [
        "What is the type of the object that comes after {tgt_type} {tgt_id} along the {dir8} path from {src_type} {src_id}?",
        "Identify the object type that follows {tgt_type} {tgt_id} in the {dir8} direction from {src_type} {src_id}.",
        "What category does the object beyond {tgt_type} {tgt_id} from {src_type} {src_id} belong to?",
        "Name the type of object found past {tgt_type} {tgt_id} continuing from {src_type} {src_id} in the {dir8}.",
    ],
}

# ---------------------------------------------------------------------------
# Template metadata
# ---------------------------------------------------------------------------

_STATIONARY_STATUSES = frozenset({"stopped", "parked", "standing", "not_standing", "sitting"})


def _is_stationary(status: str) -> bool:
    return status.lower() in _STATIONARY_STATUSES if status else False


TEMPLATE_META: Dict[str, Dict] = {
    # Direction
    "D01": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir8",        "requires": ["src_type", "tgt_type", "tgt_id", "dir8"]},
    "D02": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir8",        "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8"]},
    "D03": {"difficulty": "edge", "category": "direction",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8"]},
    "D04": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir8",        "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8"]},
    "D05": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir4",        "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir4"]},
    "D06": {"difficulty": "edge", "category": "direction",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "D07": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "D08": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir4",        "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir4"]},
    "D09": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir8",        "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8"]},
    "D10": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir4"]},
    "D11": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "D12": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir4",        "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir4"]},
    "D13": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "D14": {"difficulty": "edge", "category": "direction",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8"]},
    "D15": {"difficulty": "edge", "category": "direction",  "answer_type": "open",   "answer_source": "dir8",        "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8"]},
    # Distance
    "T01": {"difficulty": "edge", "category": "distance",   "answer_type": "open",   "answer_source": "dist_level",  "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T02": {"difficulty": "edge", "category": "distance",   "answer_type": "open",   "answer_source": "dist_level",  "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T03": {"difficulty": "edge", "category": "distance",   "answer_type": "yes_no", "answer_source": "dist==very_close", "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T04": {"difficulty": "edge", "category": "distance",   "answer_type": "yes_no", "answer_source": "dist==far",   "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T05": {"difficulty": "edge", "category": "distance",   "answer_type": "open",   "answer_source": "dist_level",  "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T06": {"difficulty": "edge", "category": "distance",   "answer_type": "yes_no", "answer_source": "dist==close", "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T07": {"difficulty": "edge", "category": "distance",   "answer_type": "open",   "answer_source": "dist_level",  "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T08": {"difficulty": "edge", "category": "distance",   "answer_type": "yes_no", "answer_source": "dist==medium","requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T09": {"difficulty": "edge", "category": "distance",   "answer_type": "open",   "answer_source": "dist_level",  "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "T10": {"difficulty": "edge", "category": "distance",   "answer_type": "yes_no", "answer_source": "dist_close_or_nearer", "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    # Existence
    "E01": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "E02": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "E03": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "dir4"]},
    "E04": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["tgt_type", "tgt_id"]},
    "E05": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["tgt_type", "tgt_id"]},
    "E06": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type"]},
    "E07": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "dir8"]},
    "E08": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id"]},
    "E09": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "dist_level"]},
    "E10": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "E11": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "dist_level"]},
    "E12": {"difficulty": "edge", "category": "existence",  "answer_type": "yes_no", "answer_source": "yes",         "requires": ["tgt_type", "tgt_id"]},
    # Status
    "S01": {"difficulty": "edge", "category": "status",     "answer_type": "open",   "answer_source": "tgt_status",  "requires": ["tgt_type", "tgt_id", "tgt_status"]},
    "S02": {"difficulty": "edge", "category": "status",     "answer_type": "yes_no", "answer_source": "tgt_moving",  "requires": ["tgt_type", "tgt_id", "tgt_status"]},
    "S03": {"difficulty": "edge", "category": "status",     "answer_type": "open",   "answer_source": "tgt_status",  "requires": ["tgt_type", "tgt_id", "tgt_status"]},
    "S04": {"difficulty": "edge", "category": "status",     "answer_type": "yes_no", "answer_source": "tgt_stationary", "requires": ["tgt_type", "tgt_id", "tgt_status"]},
    "S05": {"difficulty": "edge", "category": "status",     "answer_type": "open",   "answer_source": "src_status",  "requires": ["src_type", "src_id", "src_status"]},
    "S06": {"difficulty": "edge", "category": "status",     "answer_type": "yes_no", "answer_source": "src_moving",  "requires": ["src_type", "src_id", "src_status"]},
    "S07": {"difficulty": "edge", "category": "status",     "answer_type": "yes_no", "answer_source": "tgt_moving",  "requires": ["src_type", "src_id", "tgt_type", "tgt_status", "dir8"]},
    "S08": {"difficulty": "edge", "category": "status",     "answer_type": "open",   "answer_source": "tgt_status",  "requires": ["src_type", "src_id", "tgt_type", "tgt_status", "dir8"]},
    "S09": {"difficulty": "edge", "category": "status",     "answer_type": "yes_no", "answer_source": "tgt_stopped", "requires": ["tgt_type", "tgt_id", "tgt_status"]},
    "S10": {"difficulty": "edge", "category": "status",     "answer_type": "yes_no", "answer_source": "tgt_stationary", "requires": ["src_type", "src_id", "tgt_type", "tgt_status", "dir8"]},
    "S11": {"difficulty": "edge", "category": "status",     "answer_type": "open",   "answer_source": "tgt_status",  "requires": ["tgt_type", "tgt_id", "tgt_status"]},
    "S12": {"difficulty": "edge", "category": "status",     "answer_type": "yes_no", "answer_source": "src_moving",  "requires": ["src_type", "src_id", "src_status"]},
    # Type / Object
    "O01": {"difficulty": "edge", "category": "type",       "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["tgt_id", "tgt_type"]},
    "O02": {"difficulty": "edge", "category": "type",       "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "O03": {"difficulty": "edge", "category": "type",       "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8", "dist_level"]},
    "O04": {"difficulty": "edge", "category": "type",       "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8"]},
    "O05": {"difficulty": "edge", "category": "type",       "answer_type": "yes_no", "answer_source": "tgt_is_vehicle",  "requires": ["tgt_id", "tgt_type"]},
    "O06": {"difficulty": "edge", "category": "type",       "answer_type": "yes_no", "answer_source": "tgt_is_pedestrian", "requires": ["tgt_id", "tgt_type"]},
    "O07": {"difficulty": "edge", "category": "type",       "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["tgt_id", "tgt_type"]},
    "O08": {"difficulty": "edge", "category": "type",       "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["tgt_id", "tgt_type"]},
    # Comparison
    "C01": {"difficulty": "edge", "category": "comparison", "answer_type": "yes_no", "answer_source": "both_moving",      "requires": ["src_type", "src_id", "src_status", "tgt_type", "tgt_id", "tgt_status"]},
    "C02": {"difficulty": "edge", "category": "comparison", "answer_type": "yes_no", "answer_source": "both_stationary",  "requires": ["src_type", "src_id", "src_status", "tgt_type", "tgt_id", "tgt_status"]},
    "C03": {"difficulty": "edge", "category": "comparison", "answer_type": "yes_no", "answer_source": "same_status",      "requires": ["src_type", "src_id", "src_status", "tgt_type", "tgt_id", "tgt_status"]},
    "C04": {"difficulty": "edge", "category": "comparison", "answer_type": "yes_no", "answer_source": "src_moving_tgt_stationary", "requires": ["src_type", "src_id", "src_status", "tgt_type", "tgt_id", "tgt_status"]},
    "C05": {"difficulty": "edge", "category": "comparison", "answer_type": "yes_no", "answer_source": "tgt_moving_src_stationary", "requires": ["src_type", "src_id", "src_status", "tgt_type", "tgt_id", "tgt_status"]},
    "C06": {"difficulty": "edge", "category": "comparison", "answer_type": "open",   "answer_source": "dist_level",       "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "C07": {"difficulty": "edge", "category": "comparison", "answer_type": "yes_no", "answer_source": "yes",              "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dist_level"]},
    "C08": {"difficulty": "edge", "category": "comparison", "answer_type": "open",   "answer_source": "dir8_and_dist",    "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8", "dist_level"]},
    # L2A
    "LA01": {"difficulty": "L2", "category": "L2A", "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8", "anc_type", "anc_id"]},
    "LA02": {"difficulty": "L2", "category": "L2A", "answer_type": "yes_no", "answer_source": "yes",         "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "anc_type", "anc_id"]},
    "LA03": {"difficulty": "L2", "category": "L2A", "answer_type": "open",   "answer_source": "src_type",    "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "anc_type", "anc_id"]},
    "LA04": {"difficulty": "L2", "category": "L2A", "answer_type": "open",   "answer_source": "tgt_type",    "requires": ["src_type", "src_id", "tgt_type", "dir8", "anc_type", "anc_id"]},
    "LA05": {"difficulty": "L2", "category": "L2A", "answer_type": "open",   "answer_source": "tgt_status",  "requires": ["src_type", "src_id", "tgt_type", "tgt_status", "dir8", "anc_type", "anc_id"]},
    # L2B
    "LB01": {"difficulty": "L2", "category": "L2B", "answer_type": "yes_no", "answer_source": "beyond_exists", "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8", "beyond_id"]},
    "LB02": {"difficulty": "L2", "category": "L2B", "answer_type": "open",   "answer_source": "beyond_type",   "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "beyond_type", "beyond_id"]},
    "LB03": {"difficulty": "L2", "category": "L2B", "answer_type": "open",   "answer_source": "beyond_type",   "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8", "beyond_type"]},
    "LB04": {"difficulty": "L2", "category": "L2B", "answer_type": "open",   "answer_source": "beyond_type",   "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8", "beyond_type"]},
    "LB05": {"difficulty": "L2", "category": "L2B", "answer_type": "open",   "answer_source": "beyond_type",   "requires": ["src_type", "src_id", "tgt_type", "tgt_id", "dir8", "beyond_type"]},
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _check_requires(tvars: Dict, requires: List[str]) -> bool:
    """Return True iff all required keys are present and non-empty."""
    return all(bool(tvars.get(k)) for k in requires)


def get_applicable_templates(cell_info: Dict) -> List[str]:
    """
    Return a list of template IDs whose requirements are satisfied by cell_info.

    Args:
        cell_info: dict with keys matching TEMPLATE_META's 'requires' lists.
                   Empty string means 'not available'.
    """
    result = []
    for tid, meta in TEMPLATE_META.items():
        if _check_requires(cell_info, meta["requires"]):
            result.append(tid)
    return result


def pick_variation(tid: str) -> str:
    """
    Return one of the 4 template strings for the given template ID at random.

    Args:
        tid: template ID, e.g. "D01"

    Returns:
        A format string with {variable} placeholders.

    Raises:
        KeyError: if tid is not found in TEMPLATE_STRINGS.
    """
    variants = TEMPLATE_STRINGS[tid]
    return random.choice(variants)


def resolve_answer(tid: str, tvars: Dict) -> str:
    """
    Derive the answer string from tvars based on the template's answer_source.

    Args:
        tid:   template ID
        tvars: dict of template variables (all strings)

    Returns:
        Answer string, or empty string if it cannot be determined.
    """
    meta = TEMPLATE_META.get(tid)
    if meta is None:
        return ""

    src = meta["answer_source"]

    # Simple field lookups
    if src in ("dir8", "dir4", "dist_level",
               "tgt_type", "src_type",
               "tgt_status", "src_status",
               "anc_type", "beyond_type"):
        return tvars.get(src, "")

    # Always-yes answers
    if src == "yes":
        return "Yes"

    # beyond exists
    if src == "beyond_exists":
        return "Yes" if tvars.get("beyond_id") else "No"

    # Status-derived yes/no
    if src == "tgt_moving":
        return "Yes" if tvars.get("tgt_status", "").lower() == "moving" else "No"
    if src == "src_moving":
        return "Yes" if tvars.get("src_status", "").lower() == "moving" else "No"
    if src == "tgt_stationary":
        return "Yes" if _is_stationary(tvars.get("tgt_status", "")) else "No"
    if src == "src_stationary":
        return "Yes" if _is_stationary(tvars.get("src_status", "")) else "No"
    if src == "tgt_stopped":
        return "Yes" if tvars.get("tgt_status", "").lower() == "stopped" else "No"

    # Type-derived yes/no
    _VEHICLE_TYPES = frozenset({"car", "truck", "bus", "trailer", "motorcycle",
                                 "bicycle", "construction_vehicle", "vehicle"})
    if src == "tgt_is_vehicle":
        return "Yes" if tvars.get("tgt_type", "").lower() in _VEHICLE_TYPES else "No"
    if src == "tgt_is_pedestrian":
        return "Yes" if "pedestrian" in tvars.get("tgt_type", "").lower() else "No"

    # Distance-derived yes/no
    if src.startswith("dist=="):
        target_dist = src.split("==", 1)[1]
        return "Yes" if tvars.get("dist_level", "").lower() == target_dist else "No"
    if src == "dist_close_or_nearer":
        return "Yes" if tvars.get("dist_level", "").lower() in ("very_close", "close") else "No"

    # Comparison answer_sources
    if src == "both_moving":
        return (
            "Yes"
            if (tvars.get("src_status", "").lower() == "moving"
                and tvars.get("tgt_status", "").lower() == "moving")
            else "No"
        )
    if src == "both_stationary":
        return (
            "Yes"
            if (_is_stationary(tvars.get("src_status", ""))
                and _is_stationary(tvars.get("tgt_status", "")))
            else "No"
        )
    if src == "same_status":
        return "Yes" if tvars.get("src_status", "") == tvars.get("tgt_status", "") else "No"
    if src == "src_moving_tgt_stationary":
        return (
            "Yes"
            if (tvars.get("src_status", "").lower() == "moving"
                and _is_stationary(tvars.get("tgt_status", "")))
            else "No"
        )
    if src == "tgt_moving_src_stationary":
        return (
            "Yes"
            if (tvars.get("tgt_status", "").lower() == "moving"
                and _is_stationary(tvars.get("src_status", "")))
            else "No"
        )
    if src == "dir8_and_dist":
        d8 = tvars.get("dir8", "")
        dl = tvars.get("dist_level", "")
        if d8 and dl:
            return f"{d8}, {dl}"
        return d8 or dl

    return ""
