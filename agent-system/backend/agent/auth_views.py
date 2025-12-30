"""
User Authentication Views
"""
from django.contrib.auth import authenticate, login, logout
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import User
from .serializers import UserSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    Register a new user

    POST /api/auth/register
    Body: {
        "username": "user@example.com",
        "password": "password123",
        "email": "user@example.com"
    }
    """
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email', username)

    if not username or not password:
        return Response({
            'error': 'Username and password are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Check if user exists
    if User.objects.filter(username=username).exists():
        return Response({
            'error': 'Username already exists'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Create user
    try:
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email
        )

        # Auto-login after registration
        login(request, user)

        return Response({
            'success': True,
            'message': 'User registered successfully',
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    """
    Login user

    POST /api/auth/login
    Body: {
        "username": "user@example.com",
        "password": "password123"
    }
    """
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({
            'error': 'Username and password are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Authenticate
    user = authenticate(request, username=username, password=password)

    if user is not None:
        login(request, user)
        return Response({
            'success': True,
            'message': 'Login successful',
            'user': UserSerializer(user).data
        })
    else:
        return Response({
            'error': 'Invalid credentials'
        }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """
    Logout current user

    POST /api/auth/logout
    """
    logout(request)
    return Response({
        'success': True,
        'message': 'Logged out successfully'
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """
    Get current logged-in user

    GET /api/auth/me
    """
    return Response({
        'user': UserSerializer(request.user).data
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def check_auth(request):
    """
    Check if user is authenticated

    GET /api/auth/check
    """
    if request.user.is_authenticated:
        return Response({
            'authenticated': True,
            'user': UserSerializer(request.user).data
        })
    else:
        return Response({
            'authenticated': False
        })
