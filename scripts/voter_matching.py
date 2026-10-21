"""Transient local matching. Return aggregates, never voter-level public output."""
import unicodedata
from collections import Counter, defaultdict


def name_text(value):
    text = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ' '.join(''.join(c for c in text if c.isalnum() or c.isspace()).split())


def name_keys(row):
    first, last = row.get('first_name', ''), row.get('last_name', '')
    if first and last:
        # Use explicitly supplied middle names/suffixes; never guess initials.
        first, last = name_text(first), name_text(last)
        if not first or not last:
            return set()
        given, family = {first}, {last}
        middle, suffix = name_text(row.get('middle_name', '')), name_text(row.get('suffix', ''))
        if middle and not first.endswith(' ' + middle):
            given.add(first + ' ' + middle)
        if suffix and not last.endswith(' ' + suffix):
            family.add(last + ' ' + suffix)
        return {('parts', f, l) for f in given for l in family}
    full = row.get('full_name', '')
    if full.count(',') == 1:
        last, first = full.split(',')
        if name_text(first) and name_text(last):
            return {('parts', name_text(first), name_text(last))}
    return {('full', name_text(full))} if name_text(full) else set()


def name_index(rows):
    index = defaultdict(set)
    for i, row in enumerate(rows):
        for key in name_keys(row):
            index[row['precinct'], key].add(i)
            if key[0] == 'parts':
                # Display aliases are used only against an unsplit Name field.
                # Structured first/last fields must keep their respective roles.
                for text in (key[1] + ' ' + key[2], key[2] + ' ' + key[1]):
                    index[row['precinct'], ('display', text)].add(i)
    return index


def candidates_for(row, index):
    result = set()
    for key in name_keys(row):
        keys = [key]
        if key[0] == 'parts':
            keys += [('full', key[1] + ' ' + key[2]), ('full', key[2] + ' ' + key[1])]
        else:
            keys.append(('display', key[1]))
        for candidate in keys:
            result.update(index.get((row['precinct'], candidate), set()))
    return result


def match_precincts(voters, score_rows):
    """Exact state ID first; otherwise a unique full-name/precinct match.

    Name candidates with contradictory state IDs are never accepted. Candidate
    ambiguity is checked before ID filtering, so IDs cannot silently break a
    name tie. A score record cannot be assigned to two roster voters.
    """
    ids = defaultdict(set)
    for i, row in enumerate(score_rows):
        if row.get('vuid'):
            ids[row['vuid']].add(i)
    names, roster_names = name_index(score_rows), name_index(voters)
    proposals, outcomes = {}, {}
    for i, voter in enumerate(voters):
        exact = ids.get(voter['vuid'], set())
        if len(exact) == 1:
            proposals[i] = (next(iter(exact)), 'id')
            continue
        if len(exact) > 1:
            outcomes[i] = 'ambiguous'
            continue
        candidates = candidates_for(voter, names)
        if not candidates:
            outcomes[i] = 'unmatched'
            continue
        if len(candidates) != 1 or len(candidates_for(voter, roster_names)) > 1:
            outcomes[i] = 'ambiguous'
            continue
        target = next(iter(candidates))
        if score_rows[target].get('vuid') and score_rows[target]['vuid'] != voter['vuid']:
            outcomes[i] = 'identifier_conflict'
            continue
        proposals[i] = target, 'name'
    uses = Counter(target for target, method in proposals.values())
    groups = {}
    for i, voter in enumerate(voters):
        p = voter['precinct']
        group = groups.setdefault(p, {'values': [], 'early_voter_count': 0,
                                     'matched_count': 0, 'id_match_count': 0, 'name_match_count': 0,
                                     'unmatched_count': 0, 'ambiguous_count': 0,
                                     'identifier_conflict_count': 0})
        group['early_voter_count'] += 1
        proposal = proposals.get(i)
        if proposal:
            target, method = proposal
            if uses[target] > 1 and method != 'id':
                outcomes[i] = 'ambiguous'
                proposal = None
        if proposal:
            group['values'].append(score_rows[target]['score'])
            group['matched_count'] += 1
            group[method + '_match_count'] += 1
        else:
            group[outcomes.get(i, 'unmatched') + '_count'] += 1
    return groups
