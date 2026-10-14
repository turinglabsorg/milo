// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "MiloKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "MiloKit", targets: ["MiloKit"])],
    targets: [
        .target(name: "MiloKit"),
        .testTarget(name: "MiloKitTests", dependencies: ["MiloKit"]),
    ]
)
