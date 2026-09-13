"""Heuristic monophonic voice selection before game-range folding.

This is not a learned melody/stem classifier. It considers onset groups,
strength, register and continuity; discarded chord tails never reappear.
"""
import math


def extract_melody(raw_notes):
    valid = []
    for raw in raw_notes:
        s, e, p, v = map(float, raw[:4])
        if all(math.isfinite(x) for x in (s,e,p,v)) and e-s >= .05:
            valid.append([max(0,s),e,p,max(0,min(1,v))])
    valid.sort(key=lambda n:(n[0],n[2]))
    groups=[]
    for n in valid:
        if not groups or n[0]-groups[-1][0][0] > .04:
            groups.append([])
        groups[-1].append(n)
    selected=[]
    for group in groups:
        prior=selected[-1] if selected else None
        continuing=prior is not None and group[0][0]-prior[1] < 1.
        low=min(n[2] for n in group);high=max(n[2] for n in group)
        def score(n):
            register=(n[2]-low)/max(12,high-low)
            continuity=min(abs(n[2]-prior[2]),24)/12 if continuing else 0
            return 1.8*n[3]+.4*register+.15*min(n[1]-n[0],1)-.65*continuity
        choice=max(group,key=score)[:]
        if prior and choice[0]<prior[1]:
            # Keep a held melody over weaker, distant accompaniment attacks.
            if abs(choice[2]-prior[2])>=7 and choice[3]<prior[3]*.85:
                continue
            prior[1]=min(prior[1],choice[0])
            if prior[1]-prior[0]<.05:selected.pop()
        selected.append(choice)
    return selected
