// Usage: swift portrait-cutout.swift <input-image> <output.png>
// Cuts the subject out of an opaque portrait with macOS Vision foreground
// masking and writes a PNG with a transparent background.
// Exit 0 = written, 2 = no foreground found, 1 = other failure.
import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count == 3 else {
    FileHandle.standardError.write("usage: portrait-cutout.swift <in> <out.png>\n".data(using: .utf8)!)
    exit(1)
}
guard let input = CIImage(contentsOf: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("cannot read \(args[1])\n".data(using: .utf8)!)
    exit(1)
}
let handler = VNImageRequestHandler(ciImage: input, options: [:])
let request = VNGenerateForegroundInstanceMaskRequest()
do {
    try handler.perform([request])
    guard let obs = request.results?.first, !obs.allInstances.isEmpty else { exit(2) }
    let buffer = try obs.generateMaskedImage(ofInstances: obs.allInstances, from: handler, croppedToInstancesExtent: false)
    let out = CIImage(cvPixelBuffer: buffer)
    let ctx = CIContext()
    guard let cg = ctx.createCGImage(out, from: out.extent),
          let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: args[2]) as CFURL, UTType.png.identifier as CFString, 1, nil) else { exit(1) }
    CGImageDestinationAddImage(dest, cg, nil)
    guard CGImageDestinationFinalize(dest) else { exit(1) }
} catch {
    FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}
