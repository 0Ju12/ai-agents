from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.store.db import Store

from ..deps import get_store
from ..schemas import PlanIn, PlanOut, PlanPatch, PlanSaved

router = APIRouter(prefix="/api/plans", tags=["plans"])
NOT_FOUND = "저장한 계획을 찾을 수 없습니다."


@router.post("", response_model=PlanSaved, status_code=201)
def create_plan(body: PlanIn, store: Store = Depends(get_store)):
    plan, overlaps = store.create_plan(body.title, body.trip_date, body.start_time, body.end_time, body.items)
    return {"plan": plan, "overlaps": overlaps}


@router.get("", response_model=list[PlanOut])
def list_plans(store: Store = Depends(get_store)):
    return store.list_plans()


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, store: Store = Depends(get_store)):
    plan = store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, NOT_FOUND)
    return plan


@router.patch("/{plan_id}", response_model=PlanSaved)
def update_plan(plan_id: int, body: PlanPatch, store: Store = Depends(get_store)):
    existing=store.get_plan(plan_id)
    if existing is None:
        raise HTTPException(404, NOT_FOUND)
    fields=body.model_dump(exclude_none=True)
    if fields.get("start_time",existing["start_time"])>=fields.get("end_time",existing["end_time"]):
        raise HTTPException(422,"종료 시각은 시작 시각 이후로 입력하세요.")
    plan = store.update_plan(plan_id, **fields)
    overlaps = store.find_overlaps(plan["trip_date"], plan["start_time"], plan["end_time"], exclude_id=plan_id)
    return {"plan": plan, "overlaps": overlaps}


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, store: Store = Depends(get_store)):
    if not store.delete_plan(plan_id):
        raise HTTPException(404, NOT_FOUND)
