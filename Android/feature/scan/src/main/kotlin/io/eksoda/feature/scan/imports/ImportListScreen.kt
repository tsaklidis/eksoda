package io.eksoda.feature.scan.imports

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Pending
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import io.eksoda.core.model.ImportStatus
import io.eksoda.core.model.ImportJob
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ImportListScreen(
    onBackClick: () -> Unit,
    onReceiptClick: (String) -> Unit,
    viewModel: ImportListViewModel = hiltViewModel()
) {
    val uiState = viewModel.uiState

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Recent Imports") },
                navigationIcon = {
                    IconButton(onClick = onBackClick) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            if (uiState.isLoading && uiState.imports.isEmpty()) {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            } else if (uiState.imports.isEmpty()) {
                Text(
                    text = "No recent imports found.",
                    modifier = Modifier.align(Alignment.Center)
                )
            } else {
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(uiState.imports) { job ->
                        ImportJobItem(
                            job = job,
                            onRetryClick = { viewModel.retryImport(job.id) },
                            onReceiptClick = { job.receiptId?.let(onReceiptClick) }
                        )
                        HorizontalDivider()
                    }
                }
            }

            if (uiState.error != null) {
                Snackbar(
                    modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp)
                ) { Text(uiState.error) }
            }
        }
    }
}

@Composable
fun ImportJobItem(
    job: ImportJob,
    onRetryClick: () -> Unit,
    onReceiptClick: () -> Unit
) {
    val timeFormatter = DateTimeFormatter.ofPattern("HH:mm")
    
    ListItem(
        headlineContent = { 
            Text(
                text = job.providerCode,
                fontWeight = FontWeight.SemiBold
            )
        },
        supportingContent = {
            Column {
                Text(job.submittedUrl, maxLines = 1)
                job.error?.let { 
                    Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        trailingContent = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = job.createdAt.format(timeFormatter),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(end = 8.dp)
                )
                StatusIcon(job, onRetryClick, onReceiptClick)
            }
        }
    )
}

@Composable
fun StatusIcon(
    job: ImportJob,
    onRetryClick: () -> Unit,
    onReceiptClick: () -> Unit
) {
    when (job.status) {
        ImportStatus.PENDING -> Icon(
            Icons.Default.Pending, 
            contentDescription = "Pending",
            tint = Color.Gray
        )
        ImportStatus.COMPLETED -> IconButton(onClick = onReceiptClick) {
            Icon(
                Icons.Default.CheckCircle, 
                contentDescription = "Completed",
                tint = Color(0xFF2E7D32)
            )
        }
        ImportStatus.FAILED -> IconButton(onClick = onRetryClick) {
            Icon(
                Icons.Default.Refresh, 
                contentDescription = "Retry",
                tint = MaterialTheme.colorScheme.error
            )
        }
    }
}
