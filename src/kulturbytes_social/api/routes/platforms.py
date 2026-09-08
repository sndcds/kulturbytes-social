from fastapi import APIRouter, Depends
from kulturbytes_social.api.dependencies import platform_service
from kulturbytes_social.api.schemas import Platform
router = APIRouter(tags=['Platforms'])


@router.post('/platforms/{platform}/check-auth')
def check_auth(platform: Platform, service=Depends(platform_service)):
    service.authenticate(platform.value)
    return {'platform': platform.value, 'status': 'ok'}
