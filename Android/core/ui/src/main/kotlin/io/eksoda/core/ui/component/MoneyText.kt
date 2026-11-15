package io.eksoda.core.ui.component

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import io.eksoda.core.model.Money

@Composable
fun MoneyText(
    money: Money,
    modifier: Modifier = Modifier,
    color: Color = Color.Unspecified,
    fontWeight: FontWeight? = null
) {
    val amount = money.format()
    val currency = money.currency

    Text(
        text = buildAnnotatedString {
            withStyle(style = SpanStyle(fontWeight = fontWeight ?: FontWeight.Bold)) {
                append(amount)
            }
            append(" ")
            withStyle(style = SpanStyle(fontSize = MaterialTheme.typography.bodySmall.fontSize)) {
                append(currency)
            }
        },
        modifier = modifier,
        color = color
    )
}
