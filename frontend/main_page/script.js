(() => {
    "use strict";

    const BACKEND_URL = "http://localhost:8080";

    let room = null;
    let connected = false;

    function setupRemoteAudio() {
        if (!room) return;

        room.on(
            LivekitClient.RoomEvent.TrackSubscribed,
            (track, publication, participant) => {
                console.log(
                    "[FRIDAY] Remote track subscribed:",
                    track.kind,
                    "from:",
                    participant.identity
                );

                if (track.kind === LivekitClient.Track.Kind.Audio) {
                    const audioElement = track.attach();

                    audioElement.autoplay = true;
                    audioElement.controls = false;
                    audioElement.volume = 1.0;

                    audioElement.style.display = "none";

                    document.body.appendChild(audioElement);

                    console.log("[FRIDAY] Remote audio attached");

                    const playPromise = audioElement.play();

                    if (playPromise !== undefined) {
                        playPromise
                            .then(() => {
                                console.log("[FRIDAY] Remote audio playback started");
                            })
                            .catch((error) => {
                                console.error(
                                    "[FRIDAY] Audio playback was blocked:",
                                    error
                                );
                            });
                    }
                }
            }
        );

        room.on(
            LivekitClient.RoomEvent.TrackUnsubscribed,
            (track) => {
                console.log("[FRIDAY] Remote track unsubscribed:", track.kind);

                track.detach().forEach((element) => {
                    element.remove();
                });
            }
        );
    }

    async function startFridayVoice() {
        try {
            console.log("[FRIDAY] Starting voice connection...");

            // 1. Ask backend for a LiveKit session token
            const response = await fetch(
                `${BACKEND_URL}/api/voice/session`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        user_id: "local-user",
                        conversation_id: "main",
                        display_name: "Hari"
                    })
                }
            );

            if (!response.ok) {
                const errorText = await response.text();

                throw new Error(
                    `Backend session request failed: ${response.status} ${errorText}`
                );
            }

            const session = await response.json();

            console.log("[FRIDAY] Session received");
            console.log("[FRIDAY] Room:", session.room);

            if (!session.token || !session.livekit_url) {
                throw new Error(
                    "Backend returned an invalid LiveKit session"
                );
            }

            // 2. Create LiveKit room
            room = new LivekitClient.Room({
                adaptiveStream: true,
                dynacast: true
            });

            // 3. IMPORTANT:
            // Listen for Friday's remote audio BEFORE connecting.
            setupRemoteAudio();

            // 4. Connect to LiveKit
            await room.connect(
                session.livekit_url,
                session.token
            );

            connected = true;

            console.log("[FRIDAY] Connected to LiveKit");
            console.log("[FRIDAY] Room:", room.name);

            // 5. Turn microphone on
            await room.localParticipant.setMicrophoneEnabled(true);

            console.log("[FRIDAY] Microphone enabled");
            console.log("[FRIDAY] Voice connection ready");

        } catch (error) {
            console.error(
                "[FRIDAY] Voice connection failed:",
                error
            );
        }
    }

    async function stopFridayVoice() {
        if (!room || !connected) {
            return;
        }

        console.log("[FRIDAY] Stopping voice connection...");

        try {
            await room.localParticipant.setMicrophoneEnabled(false);

            room.disconnect();

            console.log("[FRIDAY] Disconnected from LiveKit");
        } catch (error) {
            console.error(
                "[FRIDAY] Error while disconnecting:",
                error
            );
        }

        connected = false;
        room = null;
    }

    window.addEventListener("DOMContentLoaded", () => {
        startFridayVoice();
    });

    window.addEventListener("pagehide", () => {
        stopFridayVoice();
    });

    window.addEventListener("beforeunload", () => {
        if (room) {
            room.disconnect();
        }
    });

})();