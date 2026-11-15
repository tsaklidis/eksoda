pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "Eksoda"
include(":app")
include(":core:network")
include(":core:data")
include(":core:model")
include(":core:designsystem")
include(":core:ui")
include(":feature:auth")
include(":feature:home")
include(":feature:scan")
include(":feature:receipts")
include(":feature:insights")
include(":feature:products")
include(":feature:household")
include(":feature:settings")
