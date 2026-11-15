package io.eksoda.core.designsystem.component

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector

@Composable
fun CategoryIcon(
    slug: String?,
    modifier: Modifier = Modifier,
    tint: Color = Color.Unspecified
) {
    val (icon, color) = getCategoryInfo(slug)
    Icon(
        imageVector = icon,
        contentDescription = null,
        modifier = modifier,
        tint = if (tint == Color.Unspecified) color else tint
    )
}

fun getCategoryInfo(slug: String?): Pair<ImageVector, Color> {
    return when (slug) {
        "groceries" -> Icons.Default.ShoppingBasket to Color(0xFF4CAF50)
        "dairy-and-eggs" -> Icons.Default.Egg to Color(0xFF81D4FA)
        "meat-and-fish" -> Icons.Default.SetMeal to Color(0xFFFF7043)
        "fruits-and-vegetables" -> Icons.Default.Nutrition to Color(0xFFCDDC39)
        "bakery" -> Icons.Default.BakeryDining to Color(0xFFFFC107)
        "beverages" -> Icons.Default.LocalCafe to Color(0xFF795548)
        "frozen-food" -> Icons.Default.AcUnit to Color(0xFF00BCD4)
        "snacks-and-sweets" -> Icons.Default.Cookie to Color(0xFFF06292)
        "cleaning-products" -> Icons.Default.CleaningServices to Color(0xFF009688)
        "personal-care" -> Icons.Default.Spa to Color(0xFF9575CD)
        "household-items" -> Icons.Default.Chair to Color(0xFF607D8B)
        "pet-supplies" -> Icons.Default.Pets to Color(0xFFFF9800)
        "restaurants-and-cafes" -> Icons.Default.Restaurant to Color(0xFFFF5722)
        "pharmacy-and-health" -> Icons.Default.Medication to Color(0xFFF44336)
        "fuel-and-transport" -> Icons.Default.LocalGasStation to Color(0xFF3F51B5)
        "clothing-and-footwear" -> Icons.Default.Checkroom to Color(0xFF673AB7)
        "electronics-and-appliances" -> Icons.Default.Devices to Color(0xFF2196F3)
        "services" -> Icons.Default.Handyman to Color(0xFF9E9E9E)
        else -> Icons.Default.Category to Color(0xFF9E9E9E)
    }
}
