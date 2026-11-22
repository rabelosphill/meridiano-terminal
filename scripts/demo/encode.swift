// Monta o MP4 (H.264, 1920x1080, 30 fps) a partir dos quadros capturados por record.mjs, respeitando o horário real
// de cada quadro (um quadro fica na tela até o próximo). Uso: swift scripts/demo/encode.swift <pasta-da-gravação> <saida.mp4>
import AVFoundation
import CoreGraphics
import Foundation
import ImageIO

struct Frame: Decodable { let f: String; let t: Double }
let args = CommandLine.arguments
let dir = URL(fileURLWithPath: args[1])
let out = URL(fileURLWithPath: args[2])
let frames = try JSONDecoder().decode([Frame].self, from: Data(contentsOf: dir.appendingPathComponent("index.json")))
let W = 1920, H = 1080
let fps: Int32 = 30

try? FileManager.default.removeItem(at: out)
let writer = try AVAssetWriter(outputURL: out, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
  AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: W, AVVideoHeightKey: H,
  AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 6_000_000, AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
                                    AVVideoMaxKeyFrameIntervalKey: 60],
])
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: nil)
writer.add(input)
writer.shouldOptimizeForNetworkUse = true
guard writer.startWriting() else { fatalError("writer: \(String(describing: writer.error))") }
writer.startSession(atSourceTime: .zero)

func load(_ name: String) -> CVPixelBuffer {
  let src = CGImageSourceCreateWithURL(dir.appendingPathComponent("frames").appendingPathComponent(name) as CFURL, nil)!
  let img = CGImageSourceCreateImageAtIndex(src, 0, nil)!
  var pb: CVPixelBuffer?
  CVPixelBufferCreate(nil, W, H, kCVPixelFormatType_32ARGB,
                      [kCVPixelBufferCGImageCompatibilityKey: true, kCVPixelBufferCGBitmapContextCompatibilityKey: true] as CFDictionary, &pb)
  CVPixelBufferLockBaseAddress(pb!, [])
  let ctx = CGContext(data: CVPixelBufferGetBaseAddress(pb!), width: W, height: H, bitsPerComponent: 8,
                      bytesPerRow: CVPixelBufferGetBytesPerRow(pb!), space: CGColorSpace(name: CGColorSpace.sRGB)!,
                      bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue)!
  ctx.interpolationQuality = .high
  ctx.draw(img, in: CGRect(x: 0, y: 0, width: W, height: H))
  CVPixelBufferUnlockBaseAddress(pb!, [])
  return pb!
}

let t0 = frames[0].t
let total = Int((frames.last!.t - t0) * Double(fps))
var j = 0
var current = ""
var buf: CVPixelBuffer? = nil
for i in 0...total {
  let t = Double(i) / Double(fps)
  while j + 1 < frames.count && frames[j + 1].t - t0 <= t { j += 1 }
  if frames[j].f != current { buf = load(frames[j].f); current = frames[j].f }
  while !input.isReadyForMoreMediaData { usleep(2000) }
  if !adaptor.append(buf!, withPresentationTime: CMTime(value: CMTimeValue(i), timescale: fps)) {
    fatalError("append falhou em \(i): \(String(describing: writer.error))")
  }
}
input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()
print(writer.status == .completed ? "ok: \(out.path) · \(total + 1) quadros · \(String(format: "%.1f", Double(total) / Double(fps))) s" : "erro: \(String(describing: writer.error))")
