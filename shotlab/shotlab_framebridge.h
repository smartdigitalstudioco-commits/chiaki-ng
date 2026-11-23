// ShotLab - Local decoder frame bridge for Chiaki-ng (proof-of-concept)
// This is separate from the upstream Chiaki-ng project.
// Opt in: SHOTLAB_FRAME_BRIDGE=1. Local-only UDP frames to 127.0.0.1:38517.
// No controller events or internal NBA 2K data are exported.
#pragma once
#include <QBuffer>
#include <QByteArray>
#include <QDateTime>
#include <QHostAddress>
#include <QImage>
#include <QLoggingCategory>
#include <QtNetwork/QUdpSocket>
#include <QtGlobal>
extern "C" {
#include <libavutil/frame.h>
#include <libavutil/hwcontext.h>
#include <libavutil/pixdesc.h>
#include <libavutil/pixfmt.h>
#include <libswscale/swscale.h>
}

namespace shotlab_framebridge {
class Bridge {
public:
    Bridge() : enabled_(qEnvironmentVariable("SHOTLAB_FRAME_BRIDGE") == QStringLiteral("1")) {
        if (enabled_)
            qInfo("[ShotLab] Frame-Bridge aktiv -> 127.0.0.1:38517 (TEST)");
    }
    void offer(const AVFrame *frame) {
        if (!enabled_ || !frame || frame->width < 8 || frame->height < 8)
            return;
        if ((++frames_seen_ % 3) != 0) // limit test export to ~20 fps at 60 Hz
            return;

        // Windows hardware decoders can return GPU-only frames. Copy only
        // for this opt-in test. For production, replace with async GPU readback.
        const AVPixFmtDescriptor *input_desc = av_pix_fmt_desc_get(static_cast<AVPixelFormat>(frame->format));
        if (!input_desc)
            return;
        const bool gpu_frame = frame->hw_frames_ctx || (input_desc->flags & AV_PIX_FMT_FLAG_HWACCEL);
        AVFrame *cpu_copy = nullptr;
        const AVFrame *cpu = frame;
        if (gpu_frame) {
            cpu_copy = av_frame_alloc();
            if (!cpu_copy || av_hwframe_transfer_data(cpu_copy, frame, 0) < 0) {
                if (gpu_errors_++ == 0)
                    qWarning("[ShotLab] GPU frame transfer failed. Test software decoder in Chiaki settings.");
                av_frame_free(&cpu_copy);
                return;
            }
            cpu = cpu_copy;
        }
        const auto src_fmt = static_cast<AVPixelFormat>(cpu->format);
        const AVPixFmtDescriptor *desc = av_pix_fmt_desc_get(src_fmt);
        if (!desc || (desc->flags & AV_PIX_FMT_FLAG_HWACCEL) || !cpu->data[0]) {
            av_frame_free(&cpu_copy);
            return;
        }

        constexpr int width = 960;
        const int height = cpu->height * width / cpu->width;
        if (height < 8 || height > 2000) {
            av_frame_free(&cpu_copy);
            return;
        }
        sws_ = sws_getCachedContext(sws_, cpu->width, cpu->height, src_fmt,
                                    width, height, AV_PIX_FMT_RGB24,
                                    SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
        if (!sws_) {
            av_frame_free(&cpu_copy);
            return;
        }
        QImage img(width, height, QImage::Format_RGB888);
        if (img.isNull()) {
            av_frame_free(&cpu_copy);
            return;
        }
        uint8_t *out[4] = {img.bits(), nullptr, nullptr, nullptr};
        int strides[4] = {int(img.bytesPerLine()), 0, 0, 0};
        const int ok = sws_scale(sws_, cpu->data, cpu->linesize, 0,
                                 cpu->height, out, strides);
        av_frame_free(&cpu_copy);
        if (ok <= 0)
            return;

        QByteArray jpeg;
        bool saved = false;
        constexpr int max_size = 61000;
        const QByteArray header = "SLF1|" + QByteArray::number(QDateTime::currentMSecsSinceEpoch())
                + "|" + QByteArray::number(width) + "|" + QByteArray::number(height) + "\n";
        for (int quality : {55, 38, 22}) {
            jpeg.clear();
            QBuffer buf(&jpeg);
            if (!buf.open(QIODevice::WriteOnly) || !img.save(&buf, "JPG", quality)) {
                if (jpeg_errors_++ == 0)
                    qWarning("[ShotLab] JPEG encode failed; check Qt imageformats plugins.");
                return;
            }
            if (jpeg.size() + header.size() < max_size) {
                saved = true;
                break;
            }
        }
        if (!saved) {
            if (oversize_++ == 0)
                qWarning("[ShotLab] JPEG UDP packet too big, skipping image.");
            return;
        }
        QByteArray datagram(header);
        datagram += jpeg;
        socket_.writeDatagram(datagram.constData(), datagram.size(),
                              QHostAddress::LocalHost, 38517);
        if ((++sent_ % 200) == 0)
            qInfo("[ShotLab] %d frames exported", sent_);
    }
private:
    QUdpSocket socket_;
    SwsContext *sws_ = nullptr;
    int frames_seen_ = 0;
    int sent_ = 0;
    int gpu_errors_ = 0;
    int jpeg_errors_ = 0;
    int oversize_ = 0;
    const bool enabled_;
};
inline void offer(const AVFrame *frame) {
    // Process-lifetime singleton: avoids Qt static destructor ordering.
    static Bridge *bridge = new Bridge();
    bridge->offer(frame);
}
} // namespace shotlab_framebridge
