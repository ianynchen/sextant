package com.example.orders.soap.payload;
import jakarta.xml.bind.annotation.XmlRootElement;

@XmlRootElement(name = "placeOrderRequest", namespace = "http://orders.example.com/ws")
public class PlaceOrderRequest {
    public String sku;
    public int count;
}
