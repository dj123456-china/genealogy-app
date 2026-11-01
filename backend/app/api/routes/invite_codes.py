from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.family import SyncOut
from app.schemas.invite_code import InviteCodeOut, InviteCodePayload, JoinByCodePayload
from app.services.invite_codes import create_code, join_by_code, list_codes, revoke_code, select_personal_family

router = APIRouter(prefix='/family', tags=['家族邀请码'])


@router.post('/invite-codes', response_model=InviteCodeOut, status_code=201)
def create_invite_code(payload: InviteCodePayload, family_id: int = Query(..., gt=0),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_code(db, user, family_id, payload.role)


@router.get('/invite-codes', response_model=list[InviteCodeOut])
def list_invite_codes(family_id: int = Query(..., gt=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list_codes(db, user, family_id)


@router.delete('/invite-codes/{code_id}', response_model=InviteCodeOut)
def cancel_invite_code(code_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return revoke_code(db, user, code_id)


@router.post('/join-by-code', response_model=SyncOut)
def join_family_by_code(payload: JoinByCodePayload, request: Request,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    address = request.client.host if request.client else 'unknown'
    return join_by_code(db, user, payload.code, address)


@router.post('/personal', response_model=SyncOut)
def return_to_personal_family(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return select_personal_family(db, user)
