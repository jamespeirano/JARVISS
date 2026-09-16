"""Deterministic map questions: all places, distances and turns come from local data."""
import re
from .maps import coordinate, distance, format_distance, normalized, CATEGORIES, ALIASES

INTENT = re.compile(r"\b(?:where(?:'s)?|nearest|closest|directions?|route|navigate|find|how far|how many (?:miles|kilometers|kilometres)|distance to|take me to)\b|how (?:can|do) i (?:get|go|walk)", re.I)


def parse_question(question):
    text = question.replace('’', "'").strip()
    if not INTENT.search(text): return None
    origin = None
    match = re.search(r"\b(?:i(?:'m| am) (?:on|at)|from)\s+(.+?)(?=\.\s+(?:how|where|give|find)|[,;]\s*(?:how|where|give|find)|\s+to\s+|[?;]|$)", text, re.I)
    if match:
        origin = match.group(1).strip(' .')
        text = text[:match.start()] + text[match.end():]
    nearest = re.search(r'\b(?:nearest|closest)\s+(.+)', text, re.I)
    if nearest:
        target = nearest.group(1)
    else:
        match = re.search(r'\bto\s+(.+)', text, re.I)
        if not match:
            match = re.search(r'\b(?:how far (?:is|are)|find|locate)\s+(.+)', text, re.I)
        if not match:
            match = re.search(r"\b(?:where(?:'s| is| are)?|find|locate)\s+(?:the\s+)?(.+)", text, re.I)
        target = match.group(1) if match else ''
    target = re.split(r'\s+(?:(?:and )?(?:give|show|tell) me|near me|from here|from me|to me|around here)\b|[?!;]', target, maxsplit=1, flags=re.I)[0]
    target = re.sub(r'\s+(?:please|thing)$', '', target.strip(' .'), flags=re.I)
    target = re.sub(r'^(?:the|a|an)\s+', '', target, flags=re.I)
    if target.lower() in ('there', 'here', 'it', 'that place'): target = ''
    return {'origin': origin, 'target': target, 'nearest': bool(nearest)}


def answer_map(question, profile, area, previous_route=None):
    # General questions about manuals, repairs, translation or meeting schedules
    # must not be swallowed by the broad "find/where" place parser.
    explicit=re.search(r'\b(?:nearest|closest|directions?|route|navigate|how far|how many (?:miles|kilometers|kilometres)|distance to|take me to)\b|how (?:can|do) i (?:get|go|walk)',question,re.I)
    spatial=re.search(r'\b(?:water|pharmacy|clinic|hospital|shelter|hardware|grocery|store|road|street|bridge|park|well|spring)\b',question,re.I)
    if not explicit and not spatial:return None
    if re.search(r'\b(?:manual|translate|translation|instructions|find each other)\b',question,re.I) and not explicit:return None
    intent = parse_question(question)
    if not intent: return None
    if not area:
        return ('No offline map is loaded. Use Download US offline maps in Maps while connected.', None)
    point = coordinate(profile['lat'], profile['lon']) if profile.get('lat', '') != '' and profile.get('lon', '') != '' else None
    notes = []
    if not intent['origin'] and not intent['target'] and previous_route and previous_route.get('origin'):
        point = coordinate(*previous_route['origin'])
        notes.append('Using the starting position from your preceding route.')
    if intent['origin']:
        try:
            origin = area.resolve_location(intent['origin'], point)
            point = origin['point']
            notes.append('Starting from ' + origin['name'] + '.')
            if origin.get('location_note'): notes.append(origin['location_note'])
        except ValueError as error:
            return (str(error), None)
    if point is None:
        return ('Use Maps → Find my location: search your city or town, find a familiar road or landmark, then confirm “I am here”. You can also name a recorded intersection.', None)
    if not area.contains(point):
        return ('Your position is outside the downloaded US map coverage.', None)
    target = intent['target']
    if not target:
        if previous_route and previous_route.get('destination_point'):
            places = [{'id': 'previous', 'name': previous_route['destination'], 'point': previous_route['destination_point'], 'kind': previous_route.get('destination_kind', 'place')}]
        else:
            return ('Which destination? Name a place or resource, or select a point in Maps.', None)
    else:
        # A name/coordinate route must not silently select a different same-name place.
        coordinate_target = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', target)
        if coordinate_target:
            places = [{'id': 'coordinates', 'name': target, 'point': coordinate(*coordinate_target.groups()), 'kind': 'coordinates'}]
        else:
            places = area.nearest(point, target, limit=5)
        if not places and not intent['nearest']:
            try:
                found = area.resolve_location(target, point)
                places = [dict(found, kind=found.get('kind', 'location'))]
                if found.get('location_note'): notes.append(found['location_note'])
            except ValueError:
                pass
        if not places:
            scope = area.search_note() if hasattr(area, 'search_note') else 'Search covers this downloaded area.'
            return (f'No “{target}” records found. That does not mean none exist. {scope}', None)
        exact = [p for p in places if normalized(p['name']) == normalized(target)]
        if not intent['nearest'] and exact:
            # Split road segments may share a name; road destinations remain unspecified.
            if len(exact) > 1:
                choices = '\n'.join(f"• {p['name']} — {format_distance(distance(point, p['point']))} straight-line" for p in exact)
                return (f'Several records match “{target}”. Search that name in Maps and select the intended point.\n{choices}', None)
            places = exact
        elif not intent['nearest'] and len(places) > 1:
            category = ALIASES.get(target.lower(), target.lower()).replace(' ', '_')
            if target.lower() not in CATEGORIES and not any(p.get('category') == category or p['kind'].replace(' ', '_') == category for p in places):
                choices = '\n'.join(f"• {p['name']} — {format_distance(p['distance_m'])} straight-line" for p in places)
                return (f'Which “{target}” do you mean? Give the full name, or search that name in Maps and select a result.\n{choices}', None)
    for p in places:
        p['distance_m'] = round(distance(point, p['point']))
    lines = notes + ['Closest recorded locations (straight-line distance):']
    for p in places[:3]:
        lines.append(f"• {p['name']} — {format_distance(p['distance_m'])} ({p['kind']})")
    destination = places[0]
    route = None
    if destination.get('kind') == 'road':
        lines.append('Name a cross street, or select the destination point on that road in Maps.')
    else:
        try:
            route = area.route(point, destination['point'])
            route['destination'] = destination['name']
            route['destination_kind'] = destination['kind']
            lines.append(f"Mapped walk to {destination['name']}: {format_distance(route['distance_m'])}.")
            lines.extend(f"{i}. {s['instruction']}" for i, s in enumerate(route.get('steps', [])[:4], 1))
            if len(route.get('steps',[]))>4:lines.append('Continue step by step in Maps, or open All directions.')
            if route['start_gap_m'] or route['end_gap_m']:
                lines.append(f"Check unmapped connections: {format_distance(route['start_gap_m'])} at the start; {format_distance(route['end_gap_m'])} at the destination. These are excluded from walking miles.")
        except ValueError as error:
            lines.append(str(error))
    if route and route.get('engine'): lines.append('Follow the map line and turn cues; street names are not in this routing dataset.')
    if ALIASES.get(target.lower(), target.lower()) == 'running water':
        lines.append('Current flow is unknown.')
    lines.append('Access, route conditions, and available supplies are unknown.' + (' Do not assume water is safe to drink.' if any('water' in p['kind'] or p.get('category') in ('river', 'stream', 'spring', 'lake') for p in places) else ''))
    if hasattr(area, 'search_note'): lines.append(area.search_note())
    return ('\n'.join(lines), route)
