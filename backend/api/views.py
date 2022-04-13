import django_filters.rest_framework
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from recipes.models import (CustomUser, Favorite, Follow, Ingredient,
                            IngredientInRecipe, Recipe, ShoppingList, Tag)

from .filters import IngredientFilter, RecipeFilter
from .paginators import PageNumberPaginatorModified
from .permissions import AdminOrAuthorOrReadOnly
from .serializers import (AddFavouriteRecipeSerializer, CreateRecipeSerializer,
                          IngredientSerializer, ListRecipeSerializer,
                          ShowFollowersSerializer, TagSerializer)


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = None
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = (AllowAny,)


class RecipesViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.all()
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filter_class = RecipeFilter
    pagination_class = PageNumberPaginatorModified
    permission_classes = [AdminOrAuthorOrReadOnly, ]

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ListRecipeSerializer
        return CreateRecipeSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'request': self.request})
        return context


class IngredientViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ingredient.objects.all()
    permission_classes = [AllowAny, ]
    serializer_class = IngredientSerializer
    filter_backends = [DjangoFilterBackend, ]
    filter_class = IngredientFilter
    pagination_class = None


@api_view(['GET', ])
@permission_classes([IsAuthenticated])
def show_follows(request):
    user_obj = CustomUser.objects.filter(following__user=request.user)
    paginator = PageNumberPagination()
    paginator.page_size = 6
    result_page = paginator.paginate_queryset(user_obj, request)
    serializer = ShowFollowersSerializer(
        result_page, many=True, context={'current_user': request.user})
    return paginator.get_paginated_response(serializer.data)


class FollowViewSet(APIView):
    permission_classes = (IsAuthenticated, )

    def post(self, request, user_id):
        user = request.user
        author = get_object_or_404(CustomUser, id=user_id)
        if Follow.objects.filter(user=user, author=author).exists():
            return Response(
                'Вы уже подписаны',
                status=status.HTTP_400_BAD_REQUEST)
        Follow.objects.create(user=user, author=author)
        serializer = ShowFollowersSerializer(author)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, user_id):
        user = request.user
        author = get_object_or_404(CustomUser, id=user_id)
        follow = get_object_or_404(Follow, user=user, author=author)
        follow.delete()
        return Response(
            'Удалено', status=status.HTTP_204_NO_CONTENT)


def get_post(request, recipe_id, acted_model):
    user = request.user
    recipe = get_object_or_404(Recipe, id=recipe_id)
    if acted_model.objects.filter(user=user, recipe=recipe).exists():
        return Response(
            'Рецепт уже добавлен',
            status=status.HTTP_400_BAD_REQUEST)
    acted_model.objects.create(user=user, recipe=recipe)
    serializer = AddFavouriteRecipeSerializer(recipe)
    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED)


def get_delete(request, recipe_id, acted_model):
    user = request.user
    recipe = get_object_or_404(Recipe, id=recipe_id)
    favorite_obj = get_object_or_404(acted_model, user=user, recipe=recipe)
    if not favorite_obj:
        return Response(
            'Рецепт не был добавлен',
            status=status.HTTP_400_BAD_REQUEST)
    favorite_obj.delete()
    return Response(
        'Удалено', status=status.HTTP_204_NO_CONTENT)


class FavouriteViewSet(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, recipe_id):
        return get_post(request, recipe_id, Favorite)

    def delete(self, request, recipe_id):
        return get_delete(request, recipe_id, Favorite)


class ShoppingListViewSet(APIView):
    permission_classes = (IsAuthenticated, )

    def post(self, request, recipe_id):
        return get_post(request, recipe_id, ShoppingList)

    def delete(self, request, recipe_id):
        return get_delete(request, recipe_id, ShoppingList)


class DownloadShoppingCart(APIView):
    permission_classes = (IsAuthenticated, )

    def get(self, request):
        buying_list = {}
        recipe_id = request.user.purchases.values_list('recipe__id')
        ingredients = IngredientInRecipe.objects.filter(recipe__in=recipe_id)
        ingredients = ingredients.values(
            'ingredient',
            'ingredient__name',
            'ingredient__measurement_unit'
            )
        ingredients = ingredients.annotate(amount=Sum('amount'))
        print(ingredients)
        for ingredient in ingredients:
            amount = ingredient.get('amount')
            name = ingredient.get('ingredient__name')
            measurement_unit = ingredient.get('ingredient__measurement_unit')
            if name not in buying_list:
                buying_list[name] = {
                    'measurement_unit': measurement_unit,
                    'amount': amount
                }
            else:
                buying_list[name]['amount'] = (
                    buying_list[name]['amount'] + amount)
        wishlist = []
        for item in buying_list:
            wishlist.append(f'{item} - {buying_list[item]["amount"]} '
                            f'{buying_list[item]["measurement_unit"]} \n')
        wishlist.append('\n')
        wishlist.append('FoodGram | kirilyuk.surgut@yandex.ru | 2022')
        response = HttpResponse(wishlist, 'Content-Type: text/plain')
        response['Content-Disposition'] = 'attachment; filename="wishlist.txt"'
        return response
