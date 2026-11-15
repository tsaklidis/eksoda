from rest_framework import status

from apps.common.errors import ApiError


class LineNotProduct(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "not_a_product_line"
    default_detail = "Only product lines can be linked to products. Reclassify the line first."


class SystemCategoryReadOnly(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "system_category"
    default_detail = "System categories cannot be changed. Create a household category instead."


class CategoryInUse(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "category_in_use"
    default_detail = "Products use this category. Move them to another category first."
