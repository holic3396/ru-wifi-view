import Foundation
import CoreWLAN

// JSON line output example:
// {"timestamp": 1730000000.12, "rssi": -58, "noise": -92, "tx_rate": 433.0}

func main() {
    guard let interface = CWWiFiClient.shared().interface() else {
        fputs("{\"error\":\"No WiFi interface found\"}\n", stderr)
        exit(1)
    }

    setbuf(stdout, nil)

    let interval: TimeInterval = 0.1
    while true {
        let ts = Date().timeIntervalSince1970
        let rssi = interface.rssiValue()
        let noise = interface.noiseMeasurement()
        let txRate = interface.transmitRate()

        print("{\"timestamp\":\(ts),\"rssi\":\(rssi),\"noise\":\(noise),\"tx_rate\":\(txRate)}")
        Thread.sleep(forTimeInterval: interval)
    }
}

main()
